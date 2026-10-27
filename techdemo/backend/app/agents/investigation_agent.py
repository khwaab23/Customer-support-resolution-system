"""Bounded OpenAI Responses orchestration for read-only customer investigations."""

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from app.agents.tool_definitions import MODEL_TOOLS
from app.agents.tool_executor import ToolExecutionResult, ToolExecutor
from app.core.config import Settings, get_settings
from app.prompts.investigation_agent import INVESTIGATION_AGENT_INSTRUCTIONS
from app.repositories.ticket_repository import TicketRepository
from app.schemas.agent import (
    AgentDraftResponse,
    AgentInvestigationStatus,
    AgentPolicyCitation,
    AgentIssueType,
    AgentRecommendationType,
    EvidenceReference,
    InvestigationAgentResponse,
    VerifiedFact,
)
from app.schemas.investigation import PolicyTopic
from app.tools.context import CustomerInvestigationContext

logger = logging.getLogger(__name__)

_POLICY_DEPENDENT_CATEGORIES: dict[str, PolicyTopic] = {
    "REFUND": PolicyTopic.REFUND,
    "RETURN": PolicyTopic.RETURN,
    "DAMAGED_ITEM": PolicyTopic.DAMAGED_ITEM,
}
_TOPIC_ISSUE_TYPES: dict[PolicyTopic, AgentIssueType] = {
    PolicyTopic.REFUND: AgentIssueType.REFUND,
    PolicyTopic.RETURN: AgentIssueType.RETURN,
    PolicyTopic.DAMAGED_ITEM: AgentIssueType.DAMAGED_ITEM,
}
_UNSUPPORTED_REFUND_DECISION_PATTERNS = (
    r"\brefund\s+(?:must|should)\s+be\s+(?:issued|processed)\b",
    r"\bensure\b[^.]{0,100}\brefund\s+(?:is\s+)?(?:issued|processed)\b",
    r"\b(?:customer|you)\s+(?:is|are)\s+eligible\b",
    r"\beligible\s+for\s+(?:a\s+)?refund\b",
    r"\b(?:issue|process|approve)\s+(?:the\s+)?refund\b",
)


class EvidenceValidationError(ValueError):
    """A model response referenced evidence that was not returned in this run."""

    def __init__(self, diagnostic_code: str) -> None:
        super().__init__(diagnostic_code)
        self.diagnostic_code = diagnostic_code


class InvestigationAgent:
    """Coordinate a model with fixed tools; the model never receives identity control."""

    def __init__(
        self,
        ticket_repository: TicketRepository,
        tool_executor: ToolExecutor,
        *,
        settings: Settings | None = None,
        client: object | None = None,
    ) -> None:
        self._tickets = ticket_repository
        self._executor = tool_executor
        self._settings = settings or get_settings()
        self._client = client

    def investigate(
        self,
        ticket_id: str,
        context: CustomerInvestigationContext,
    ) -> InvestigationAgentResponse:
        """Return a source-grounded response for an authorized ticket only."""
        ticket = self._tickets.get_by_id(ticket_id)
        if ticket is None or ticket.customer_id != context.customer_id:
            return self._safe_response(
                ticket_id,
                AgentInvestigationStatus.NOT_FOUND_OR_NOT_AUTHORIZED,
                "The requested ticket could not be found.",
            )

        try:
            client = self._get_client()
            response = client.responses.create(
                model=self._settings.openai_agent_model,
                instructions=INVESTIGATION_AGENT_INSTRUCTIONS,
                input=json.dumps(
                    {
                        "ticket_id": ticket.ticket_id,
                        "ticket_category": ticket.category,
                        "ticket_message": ticket.message,
                        "linked_order_id": ticket.order_id,
                    }
                ),
                tools=list(MODEL_TOOLS),
                parallel_tool_calls=False,
                max_tool_calls=self._settings.agent_max_tool_calls,
                max_output_tokens=self._settings.agent_max_output_tokens,
                timeout=self._settings.agent_request_timeout_seconds,
            )
        except Exception:
            self._diagnostic("OPENAI_API_ERROR_INITIAL")
            return self._safe_response(
                ticket.ticket_id,
                AgentInvestigationStatus.MODEL_ERROR,
                "Investigation is temporarily unavailable. Please try again later.",
            )

        executions: list[ToolExecutionResult] = []
        seen_calls: set[tuple[str, str]] = set()
        attempted_policy_topics: set[PolicyTopic] = set()
        required_policy_topic = self._required_policy_topic(ticket.category)
        for _ in range(self._settings.agent_max_tool_rounds):
            calls = self._function_calls(response)
            if not calls:
                break
            if len(executions) + len(calls) > self._settings.agent_max_tool_calls:
                self._diagnostic("TOOL_CALL_LIMIT_REACHED")
                return self._safe_response(
                    ticket.ticket_id,
                    AgentInvestigationStatus.TOOL_LIMIT_REACHED,
                    "Investigation needs more evidence than the safe tool limit allows.",
                    tools=[execution.tool_name for execution in executions],
                )

            outputs: list[dict[str, str]] = []
            for call in calls:
                name = str(getattr(call, "name", ""))
                arguments = str(getattr(call, "arguments", "{}"))
                if name == "lookup_policy":
                    topic = self._policy_topic_from_arguments(arguments)
                    if topic is not None:
                        attempted_policy_topics.add(topic)
                signature = (name, arguments)
                if signature in seen_calls:
                    execution = ToolExecutionResult.model_validate(
                        {
                            "tool_name": name,
                            "ok": False,
                            "error": {
                                "code": "DUPLICATE_TOOL_CALL",
                                "message": "This identical evidence request was already attempted.",
                            },
                        }
                    )
                else:
                    seen_calls.add(signature)
                    execution = self._executor.execute(name, arguments, context)
                if not execution.ok:
                    self._diagnostic(
                        f"TOOL_EXECUTION_FAILURE:{execution.error.code if execution.error else 'UNKNOWN'}",
                        tool_name=name,
                    )
                executions.append(execution)
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(getattr(call, "call_id", "")),
                        "output": self._model_tool_output(execution),
                    }
                )
            try:
                response = client.responses.create(
                    model=self._settings.openai_agent_model,
                    previous_response_id=getattr(response, "id"),
                    input=outputs,
                    tools=list(MODEL_TOOLS),
                    parallel_tool_calls=False,
                    max_tool_calls=max(
                        self._settings.agent_max_tool_calls - len(executions), 0
                    ),
                    max_output_tokens=self._settings.agent_max_output_tokens,
                    timeout=self._settings.agent_request_timeout_seconds,
                )
            except Exception:
                self._diagnostic("OPENAI_API_ERROR_TOOL_LOOP")
                return self._safe_response(
                    ticket.ticket_id,
                    AgentInvestigationStatus.MODEL_ERROR,
                    "Investigation is temporarily unavailable. Please try again later.",
                    tools=[execution.tool_name for execution in executions],
                )
        else:
            self._diagnostic("TOOL_ROUND_LIMIT_REACHED")
            return self._safe_response(
                ticket.ticket_id,
                AgentInvestigationStatus.TOOL_LIMIT_REACHED,
                "Investigation reached the safe tool-round limit.",
                tools=[execution.tool_name for execution in executions],
            )

        if not any(execution.ok for execution in executions):
            self._diagnostic("INSUFFICIENT_BUSINESS_EVIDENCE")
            return self._safe_response(
                ticket.ticket_id,
                AgentInvestigationStatus.INSUFFICIENT_EVIDENCE,
                "No verified evidence was available for this investigation.",
                tools=[execution.tool_name for execution in executions],
            )

        automatic_policy_execution: ToolExecutionResult | None = None
        if (
            required_policy_topic is not None
            and required_policy_topic not in attempted_policy_topics
        ):
            if len(executions) >= self._settings.agent_max_tool_calls:
                self._diagnostic("TOOL_CALL_LIMIT_REACHED")
                return self._safe_response(
                    ticket.ticket_id,
                    AgentInvestigationStatus.TOOL_LIMIT_REACHED,
                    "Investigation needs more evidence than the safe tool limit allows.",
                    tools=[execution.tool_name for execution in executions],
                )
            try:
                automatic_policy_execution = self._executor.execute(
                    "lookup_policy",
                    {"topic": required_policy_topic.value},
                    context,
                )
            except Exception:
                automatic_policy_execution = ToolExecutionResult.model_validate(
                    {
                        "tool_name": "lookup_policy",
                        "ok": False,
                        "error": {
                            "code": "TOOL_UNAVAILABLE",
                            "message": "The requested evidence is unavailable.",
                        },
                    }
                )
            attempted_policy_topics.add(required_policy_topic)
            executions.append(automatic_policy_execution)
            if not automatic_policy_execution.ok:
                self._diagnostic(
                    "TOOL_EXECUTION_FAILURE:"
                    f"{automatic_policy_execution.error.code if automatic_policy_execution.error else 'UNKNOWN'}",
                    tool_name="lookup_policy",
                )
            self._diagnostic("AUTOMATIC_POLICY_LOOKUP", tool_name="lookup_policy")

        try:
            final_response = client.responses.create(
                model=self._settings.openai_agent_model,
                previous_response_id=getattr(response, "id"),
                input=self._final_generation_input(
                    required_policy_topic,
                    automatic_policy_execution,
                ),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "investigation_agent_response",
                        "strict": True,
                        "schema": AgentDraftResponse.model_json_schema(),
                    }
                },
                max_output_tokens=self._settings.agent_max_output_tokens,
                timeout=self._settings.agent_request_timeout_seconds,
            )
        except Exception:
            self._diagnostic("OPENAI_API_ERROR_FINAL")
            return self._safe_response(
                ticket.ticket_id,
                AgentInvestigationStatus.MODEL_ERROR,
                "Investigation is temporarily unavailable. Please try again later.",
                tools=[execution.tool_name for execution in executions],
            )

        try:
            raw_output = str(getattr(final_response, "output_text", ""))
            try:
                draft_data = json.loads(raw_output)
            except json.JSONDecodeError:
                self._diagnostic("INVALID_MODEL_JSON")
                raise
            try:
                draft = AgentDraftResponse.model_validate(draft_data)
            except ValidationError:
                self._diagnostic("PYDANTIC_SCHEMA_VALIDATION_FAILURE")
                raise
            return self._validate_draft(
                ticket.ticket_id,
                draft,
                executions,
                required_policy_topic=required_policy_topic,
            )
        except EvidenceValidationError as exc:
            self._diagnostic(exc.diagnostic_code)
            return self._safe_response(
                ticket.ticket_id,
                AgentInvestigationStatus.INSUFFICIENT_EVIDENCE,
                "The investigation response could not be verified against available evidence.",
                tools=[execution.tool_name for execution in executions],
            )
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError):
            return self._safe_response(
                ticket.ticket_id,
                AgentInvestigationStatus.INSUFFICIENT_EVIDENCE,
                "The investigation response could not be verified against available evidence.",
                tools=[execution.tool_name for execution in executions],
            )

    def _validate_draft(
        self,
        ticket_id: str,
        draft: AgentDraftResponse,
        executions: list[ToolExecutionResult],
        *,
        required_policy_topic: PolicyTopic | None,
    ) -> InvestigationAgentResponse:
        successful = {
            execution.tool_name: execution.result
            for execution in executions
            if execution.ok and execution.result is not None
        }
        verified_facts = [
            self._resolve_fact(reference, successful) for reference in draft.evidence_references
        ]
        citation_keys = self._policy_citation_keys(executions, required_policy_topic)
        for citation in draft.policy_citations:
            key = (
                citation.policy_id,
                citation.policy_version,
                citation.source,
                citation.section_heading,
                citation.effective_date.isoformat() if citation.effective_date else None,
            )
            if key not in citation_keys:
                raise EvidenceValidationError("MISSING_OR_FABRICATED_POLICY_CITATION")

        if required_policy_topic is not None:
            policy_evidence = self._has_retrieved_policy(executions, required_policy_topic)
            if not policy_evidence:
                self._diagnostic("POLICY_EVIDENCE_UNAVAILABLE")
                return self._policy_review_required_response(
                    ticket_id,
                    verified_facts,
                    executions,
                    required_policy_topic,
                    missing_information=draft.missing_information,
                )
            if not draft.policy_citations:
                self._diagnostic("POLICY_CITATION_REQUIRED")
                return self._policy_review_required_response(
                    ticket_id,
                    verified_facts,
                    executions,
                    required_policy_topic,
                    missing_information=draft.missing_information,
                )
            if (
                draft.issue_type is not _TOPIC_ISSUE_TYPES[required_policy_topic]
                or draft.recommendation_type is not AgentRecommendationType.HUMAN_REVIEW
                or not draft.requires_human_review
                or self._contains_unsupported_refund_decision(draft)
            ):
                self._diagnostic("UNSUPPORTED_POLICY_DECISION_REWRITTEN")
                return self._policy_review_required_response(
                    ticket_id,
                    verified_facts,
                    executions,
                    required_policy_topic,
                    missing_information=draft.missing_information,
                )

        combined_text = " ".join(
            [draft.customer_explanation, *draft.recommended_next_steps]
        ).casefold()
        if "approve refund" in combined_text or "execute refund" in combined_text:
            raise EvidenceValidationError("PROHIBITED_REFUND_ACTION_LANGUAGE")
        return InvestigationAgentResponse(
            ticket_id=ticket_id,
            issue_type=draft.issue_type,
            investigation_status=AgentInvestigationStatus.COMPLETE,
            recommendation_type=draft.recommendation_type,
            customer_explanation=draft.customer_explanation,
            verified_facts=verified_facts,
            policy_citations=draft.policy_citations,
            missing_information=draft.missing_information,
            recommended_next_steps=draft.recommended_next_steps,
            requires_human_review=draft.requires_human_review,
            tools_executed=[execution.tool_name for execution in executions],
        )

    @staticmethod
    def _resolve_fact(
        reference: EvidenceReference,
        results: dict[str, dict[str, Any] | None],
    ) -> VerifiedFact:
        payload = results.get(reference.tool_name)
        if payload is None:
            raise EvidenceValidationError("INVALID_EVIDENCE_JSON_POINTER")
        value: Any = payload
        for raw_part in reference.json_pointer.lstrip("/").split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if isinstance(value, dict) and part in value:
                value = value[part]
            elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
                value = value[int(part)]
            else:
                raise EvidenceValidationError("INVALID_EVIDENCE_JSON_POINTER")
        return VerifiedFact(
            tool_name=reference.tool_name,
            json_pointer=reference.json_pointer,
            value=json.dumps(value, ensure_ascii=False, sort_keys=True),
        )

    @staticmethod
    def _policy_citation_keys(
        executions: list[ToolExecutionResult],
        required_topic: PolicyTopic | None,
    ) -> set[tuple[str, str, str, str, str | None]]:
        """Use only passages returned by the applicable lookup in this run."""
        keys: set[tuple[str, str, str, str, str | None]] = set()
        for execution in executions:
            policy_result = execution.result if execution.ok else None
            if (
                execution.tool_name != "lookup_policy"
                or not isinstance(policy_result, dict)
                or (
                    required_topic is not None
                    and policy_result.get("topic") != required_topic.value
                )
            ):
                continue
            for policy in policy_result.get("policies", []):
                if not isinstance(policy, dict):
                    continue
                values = (
                    policy.get("policy_id"),
                    policy.get("policy_version"),
                    policy.get("source"),
                    policy.get("section_heading"),
                )
                effective_date = policy.get("effective_date")
                if all(isinstance(value, str) and value for value in values) and (
                    effective_date is None or isinstance(effective_date, str)
                ):
                    keys.add((*values, effective_date))  # type: ignore[arg-type]
        return keys

    @staticmethod
    def _required_policy_topic(category: str) -> PolicyTopic | None:
        return _POLICY_DEPENDENT_CATEGORIES.get(category.strip().upper())

    @staticmethod
    def _policy_topic_from_arguments(raw_arguments: str) -> PolicyTopic | None:
        try:
            arguments = json.loads(raw_arguments)
            return PolicyTopic(arguments.get("topic"))
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
            return None

    @staticmethod
    def _has_retrieved_policy(
        executions: list[ToolExecutionResult],
        topic: PolicyTopic,
    ) -> bool:
        return any(
            execution.ok
            and execution.tool_name == "lookup_policy"
            and isinstance(execution.result, dict)
            and execution.result.get("topic") == topic.value
            and execution.result.get("outcome") == "FOUND"
            and isinstance(execution.result.get("policies"), list)
            and bool(execution.result["policies"])
            for execution in executions
        )

    def _policy_review_required_response(
        self,
        ticket_id: str,
        verified_facts: list[VerifiedFact],
        executions: list[ToolExecutionResult],
        topic: PolicyTopic,
        *,
        missing_information: list[str],
    ) -> InvestigationAgentResponse:
        """Return verified facts while withholding any policy eligibility decision."""
        missing = [
            *missing_information,
            "Policy eligibility has not been determined from the available evidence.",
        ]
        return InvestigationAgentResponse(
            ticket_id=ticket_id,
            issue_type=_TOPIC_ISSUE_TYPES[topic],
            investigation_status=AgentInvestigationStatus.POLICY_REVIEW_REQUIRED,
            recommendation_type=AgentRecommendationType.HUMAN_REVIEW,
            customer_explanation=(
                "Verified transaction history was retrieved, but policy eligibility "
                "requires human review."
            ),
            verified_facts=verified_facts,
            policy_citations=self._retrieved_policy_citations(executions, topic),
            missing_information=list(dict.fromkeys(missing)),
            recommended_next_steps=[
                "Escalate for human review to verify eligibility and determine next "
                "steps under the applicable policy."
            ],
            requires_human_review=True,
            tools_executed=[execution.tool_name for execution in executions],
        )

    @staticmethod
    def _retrieved_policy_citations(
        executions: list[ToolExecutionResult],
        topic: PolicyTopic,
    ) -> list[AgentPolicyCitation]:
        citations: list[AgentPolicyCitation] = []
        seen: set[tuple[str, str, str, str, str | None]] = set()
        for execution in executions:
            result = execution.result if execution.ok else None
            if (
                execution.tool_name != "lookup_policy"
                or not isinstance(result, dict)
                or result.get("topic") != topic.value
            ):
                continue
            for policy in result.get("policies", []):
                if not isinstance(policy, dict):
                    continue
                try:
                    citation = AgentPolicyCitation.model_validate(
                        {
                            "policy_id": policy.get("policy_id"),
                            "policy_version": policy.get("policy_version"),
                            "source": policy.get("source"),
                            "section_heading": policy.get("section_heading"),
                            "effective_date": policy.get("effective_date"),
                        }
                    )
                except ValidationError:
                    continue
                key = (
                    citation.policy_id,
                    citation.policy_version,
                    citation.source,
                    citation.section_heading,
                    citation.effective_date.isoformat() if citation.effective_date else None,
                )
                if key not in seen:
                    seen.add(key)
                    citations.append(citation)
        return citations

    @staticmethod
    def _contains_unsupported_refund_decision(draft: AgentDraftResponse) -> bool:
        text = " ".join(
            [draft.customer_explanation, *draft.recommended_next_steps]
        ).casefold()
        return any(re.search(pattern, text) is not None for pattern in _UNSUPPORTED_REFUND_DECISION_PATTERNS)

    def _final_generation_input(
        self,
        required_policy_topic: PolicyTopic | None,
        automatic_policy_execution: ToolExecutionResult | None,
    ) -> str:
        """Give final generation bounded backend-enforced policy evidence."""
        base = "Return the final investigation response as the required JSON schema."
        if required_policy_topic is None:
            return base
        requirement = (
            f" This is a policy-dependent {required_policy_topic.value} investigation. "
            "Choose HUMAN_REVIEW and do not decide eligibility or approve an action."
        )
        if automatic_policy_execution is None:
            return base + requirement
        return (
            base
            + requirement
            + " The backend automatically retrieved the following policy-lookup result; "
            "use citations only when its passages support them: "
            + self._model_tool_output(automatic_policy_execution)
        )

    @staticmethod
    def _function_calls(response: object) -> list[object]:
        return [
            item
            for item in getattr(response, "output", [])
            if getattr(item, "type", None) == "function_call"
        ]

    @staticmethod
    def _model_tool_output(execution: ToolExecutionResult) -> str:
        """Give the model the same JSON root used for evidence references."""
        if execution.ok and execution.result is not None:
            return json.dumps(execution.result, ensure_ascii=False, separators=(",", ":"))
        return json.dumps(
            {"error": execution.error.model_dump() if execution.error else {}},
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _diagnostic(self, code: str, *, tool_name: str | None = None) -> None:
        """Development-only reason codes with no prompts, credentials, or payloads."""
        if (
            self._settings.app_environment == "development"
            and self._settings.agent_diagnostics_enabled
        ):
            logger.info(
                "ai_investigation_diagnostic code=%s tool=%s",
                code,
                tool_name or "none",
            )

    def _get_client(self):
        if self._client is None:
            if not self._settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is required for AI investigation.")
            from openai import OpenAI

            self._client = OpenAI(api_key=self._settings.openai_api_key)
        return self._client

    @staticmethod
    def _safe_response(
        ticket_id: str,
        status: AgentInvestigationStatus,
        explanation: str,
        *,
        tools: list[str] | None = None,
    ) -> InvestigationAgentResponse:
        return InvestigationAgentResponse(
            ticket_id=ticket_id,
            issue_type=AgentIssueType.UNKNOWN,
            investigation_status=status,
            customer_explanation=explanation,
            missing_information=[explanation],
            recommended_next_steps=["Request human support if further assistance is needed."],
            requires_human_review=True,
            tools_executed=tools or [],
        )
