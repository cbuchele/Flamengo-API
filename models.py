
from sqlalchemy import Boolean, Column, String, TIMESTAMP, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base

class Client(Base):
    __tablename__ = 'clients'

    id = Column(String(50), primary_key=True, index=True)
    nome = Column(String(50))
    telefone = Column(String(20), nullable=True)
    email = Column(String(50))
    viagens = Column(String(100))
    comprovante = Column(String(200))
    passagens = Column(String(200))
    role = Column(String(10))
    confirmed = Column(Boolean())
    deleted = Column(DateTime, nullable=True)  # Use DateTime instead of TIMESTAMP

    reservations = relationship("Reservation", back_populates="client")  # Corrected back_populates
    payments = relationship("Payment", back_populates="client")  # Add relationship


    class Config:
        orm_mode = True

class Onibus(Base):
    __tablename__ = 'onibus'

    id = Column(String(50), primary_key=True, index=True)
    foto_casa = Column(String(200))
    foto_visita = Column(String(200))
    evento = Column(String(100))
    descricao = Column(String(255))
    horario = Column(String(50))
    vagas = Column(Integer)

    reservations = relationship("Reservation", back_populates="onibus")  # Corrected back_populates
    payments = relationship("Payment", back_populates="onibus")  # Add relationship


    class Config:
        orm_mode = True

class Reservation(Base):
    __tablename__ = 'reservations'

    id = Column(String(50), primary_key=True, index=True)
    client_id = Column(String(50), ForeignKey('clients.id'))
    onibus_id = Column(String(50), ForeignKey('onibus.id'))
    seat_row = Column(Integer)
    seat_column = Column(Integer)
    timestamp = Column(DateTime)  # Use DateTime instead of TIMESTAMP
    confirmed = Column(Boolean(), default=False)  # Add confirmed field


    client = relationship("Client", back_populates="reservations")  # Corrected back_populates
    onibus = relationship("Onibus", back_populates="reservations")  # Corrected back_populates

    class Config:
        orm_mode = True


class Payment(Base):
    __tablename__ = 'payments'

    id = Column(String(50), primary_key=True, index=True)
    client_id = Column(String(50), ForeignKey('clients.id'))
    onibus_id = Column(String(50), ForeignKey('onibus.id'))
    payment_id = Column(String(50))  # Payment ID from Mercado Pago NEEDS TO BE UNIQUE SO WE CANT HAVE 2 of THE SAME PAYMENT
    status = Column(String(50))  # Payment status
    timestamp = Column(DateTime)
    transaction_amount = Column(Integer)
    email = Column(String(100))
    approved = Column(Boolean(), default=False)
    seats = Column(JSON)  # Store seats information as JSON


    client = relationship("Client", back_populates="payments")
    onibus = relationship("Onibus", back_populates="payments")

    class Config:
        orm_mode = True

