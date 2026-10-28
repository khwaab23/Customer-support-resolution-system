from pydantic import BaseModel


class WorkflowStartResponse(BaseModel):
    workflow_id: str
    workflow_status: str
    review_created: bool
