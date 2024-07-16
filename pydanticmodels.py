
from pydantic import BaseModel, Field, EmailStr, Json
from typing import List, Optional, Dict

class ReservationDetails(BaseModel):
    client_id: str
    onibus_id: str
    seats: list[dict]
    email: EmailStr


class Seat(BaseModel):
    row: int
    column: int

class ClientBase(BaseModel):
    id: Optional[str] = Field(None, alias="id")
    nome: Optional[str] = Field(None, alias="nome")
    telefone: Optional[str] = Field(None, alias="telefone")
    viagens: Optional[str]
    email: Optional[str]
    role: Optional[str]
    comprovante: Optional[str]
    confirmed: Optional[bool]
    deleted: Optional[str]

class OnibusBase(BaseModel):
    id: Optional[str] = Field(None, alias="id")
    evento: Optional[str]
    foto_casa: Optional[str]
    foto_visita: Optional[str]
    descricao: Optional[str]
    vagas: Optional[int]
    horario: Optional[str]

# Example usage of the models
class Seat(BaseModel):
    row: int
    column: int

class ReserveRequest(BaseModel):
    client_id: str
    seats: List[Seat]


class PaymentData(BaseModel):
    transaction_amount: float
    email: str


class NotificationData(BaseModel):
    action: str
    api_version: str
    data: Dict[str, str]
    date_created: str
    id: int
    live_mode: bool
    type: str
    user_id: str

class ReservationResponse(BaseModel):
    id: str
    client_id: str
    onibus_id: str
    seat_row: int
    seat_column: int
    timestamp: str

    class Config:
        orm_mode = True



class PaymentResponse(BaseModel):
    id: str
    client_id: str
    onibus_id: str
    payment_id: str
    status: str
    timestamp: str
    seat_row: int
    seat_column: int
    amount: float
    approved: bool



class PaymentStatusRequest(BaseModel):
    payment_id: str

class PaymentUpdate(BaseModel):
    status: str
    amount: Optional[float] = None

class DBPaymentData(BaseModel):
    transaction_amount: float
    email: str
    client_id: str
    onibus_id: str
    payment_id: str
    status: str
    timestamp: str
    approved: str
    seats: List[Seat]
