from pydantic import BaseModel, Field
from typing import List, Optional

class ExtractedField(BaseModel):
    field_name: str = Field(...)
    extracted_value: Optional[str]
    confidence_score: float = Field(default=0.99)
    is_corrected: bool = Field(default=False)
    corrected_value: Optional[str]

class HTRSchema(BaseModel):
    document_id: str = Field(...)
    source_type: str = Field(...)
    fields: List[ExtractedField]

# Mandate Card Target Fields: SURNAME, NAME, OCCUPATION, GROSS MONTHLY INCOME
# National ID Target Fields: ID_NUMBER, DATE_OF_BIRTH, GENDER, NATIONALITY
