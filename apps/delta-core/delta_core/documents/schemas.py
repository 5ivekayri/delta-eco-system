from pydantic import Field, field_validator
from delta_contracts.devices import StrictModel


class Edit(StrictModel):
    block_id: str = Field(pattern=r'^p[0-9]+$', max_length=20)
    old_text: str = Field(max_length=20000)
    text: str = Field(max_length=20000)

    @field_validator('text')
    @classmethod
    def xml_text(cls, value):
        if any(ord(c)<32 and c not in '\n\r\t' or 0xD800<=ord(c)<=0xDFFF or ord(c) in {0xFFFE,0xFFFF} for c in value):
            raise ValueError('Unsupported control character')
        return value


class Changes(StrictModel):
    edits: list[Edit] = Field(default_factory=list, max_length=100)
    append: list[str] = Field(default_factory=list, max_length=30)

    @field_validator('append')
    @classmethod
    def append_text(cls, values):
        for value in values:
            if len(value)>20000:raise ValueError('Paragraph too long')
            Edit.xml_text(value)
        return values


class SaveInput(Changes):
    base_revision: int = Field(ge=1)


class AIInput(StrictModel):
    revision: int = Field(ge=1)
    instruction: str = Field(min_length=1, max_length=3000)
    block_ids: list[str] = Field(default_factory=list, max_length=100)
    @field_validator('instruction')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():raise ValueError('Empty instruction')
        return value.strip()
