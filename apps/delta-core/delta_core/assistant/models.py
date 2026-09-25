from sqlalchemy import JSON,String,Text
from sqlalchemy.orm import Mapped,mapped_column
from delta_contracts.storage import Record
from delta_core.db import Base


class Interaction(Record,Base):
    __tablename__='assistant_history'
    user_message:Mapped[str]=mapped_column(Text)
    assistant_text:Mapped[str]=mapped_column(Text)
    tool_calls:Mapped[list]=mapped_column(JSON,default=list)
    tool_results:Mapped[list]=mapped_column(JSON,default=list)
    device_id:Mapped[str|None]=mapped_column(String(36),nullable=True)
