from decimal import Decimal
from sqlalchemy import String, Numeric, Integer
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Account(Base):
    __tablename__ = "accounts"

    vpa: Mapped[str] = mapped_column(String, primary_key=True)
    holder_name: Mapped[str] = mapped_column(String, nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(precision=19, scale=2), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __mapper_args__ = {"version_id_col": version}

    def __repr__(self):
        return f"<Account vpa={self.vpa} balance={self.balance}>"
