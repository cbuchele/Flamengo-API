from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status, Request, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pydanticmodels import ClientBase,OnibusBase,ReserveRequest, PaymentData, NotificationData, ReservationResponse, Seat, ReservationDetails, PaymentResponse, DBPaymentData, PaymentResponse, PaymentUpdate
from typing import Generator, List, Tuple
import models
from fastapi.middleware.cors import CORSMiddleware
from database import engine, SessionLocal
from datetime import datetime, timedelta
import os
import uuid
import mercadopago
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials
from firebase_admin import storage
from string import Template  # Import Template from string module
from fastapi.responses import JSONResponse
from email.mime.multipart import MIMEMultipart  # Import MIMEMultipart
from email.mime.text import MIMEText  # Import MIMEText
import smtplib
from requests.exceptions import RequestException
import requests
import time
from threading import Thread



load_dotenv()

cred = credentials.Certificate('./firebasekey.json')
firebase_admin.initialize_app(cred, {
    'storageBucket': 'flamengoexcursao.appspot.com'
})

bucket = storage.bucket()


app = FastAPI(ssl_keyfile="./private.key", ssl_certfile="./certificate.crt")

models.Base.metadata.create_all(bind=engine)

access_token = os.getenv("MERCADO_PAGO_ACCESS_TOKEN")
sdk = mercadopago.SDK(access_token)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://189.107.236.131:0",
    "https://www.flamengoexcurcoesvrmaracana.online",
    "https://flamengoexcurcoesvrmaracana.vercel.app",
    "https://e52e-2804-2e0c-fc25-b600-a8d-40ae-f298-9b10.ngrok-free.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# Define the directory where files will be saved
UPLOAD_DIR = "./uploads"

# Ensure the upload directory exists, create it if necessary
os.makedirs(UPLOAD_DIR, exist_ok=True)



# Load the email template
def load_template():
    with open("email_template.html", "r", encoding="utf-8") as file:
        template = Template(file.read())
    return template

# Send email function
def send_email(to_email: str, subject: str, body: str):
    try:
        # Email account credentials
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_PASSWORD")

        # Create the email
        msg = MIMEMultipart()
        msg["From"] = gmail_user
        msg["To"] = to_email
        msg["Subject"] = subject

        # Attach the HTML body
        msg.attach(MIMEText(body, "html"))

        # Send the email
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, to_email, msg.as_string())

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/send-confirmation-email/")
async def send_confirmation_email(details: ReservationDetails, background_tasks: BackgroundTasks):
    try:
        # Load the email template
        template = load_template()

        # Ensure seats are converted to strings
        seats_str = [str(seat) for seat in details.seats]

        # Render the email content
        email_content = template.substitute(
            client_id=details.client_id,
            onibus_id=details.onibus_id,
            seats=", ".join(seats_str),
        )

        # Send the email in the background
        background_tasks.add_task(send_email, details.email, "Confirmação de Reserva", email_content)

        return JSONResponse(status_code=200, content={"message": "Email de confirmação enviado com sucesso"})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def save_file_locally(file: UploadFile, category: str, client_id: str, db: Session):
    # Generate a unique filename
    file_extension = file.filename.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    # Open a file in write-binary mode and write the file contents
    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())
    # Save file metadata to the database
    db_file = models.File(category=category, client_id=client_id, file_path=file_path)
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    return db_file

@app.post("/upload/")
async def upload_file(client_id: str, category: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    # Check if the client exists
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    # Upload the file to Firebase Storage
    blob = bucket.blob(f"{category}/{client_id}/{file.filename}")
    blob.upload_from_file(file.file, content_type=file.content_type)

    # Optionally, make the file publicly accessible
    blob.make_public()

    return {"file_url": blob.public_url}

@app.post("/upload/home/")
async def upload_foto_home(onibus_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    # Check if the onibus exists
    onibus = db.query(models.Onibus).filter(models.Onibus.id == onibus_id).first()
    if not onibus:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onibus not found")

    # Upload the file to Firebase Storage
    blob = bucket.blob(f"onibus/{onibus_id}/home/{file.filename}")
    blob.upload_from_file(file.file, content_type=file.content_type)
    blob.make_public()  # Optionally make the file publicly accessible

    # Update the Onibus record with the new foto_home URL
    onibus.foto_casa = blob.public_url
    db.commit()

    return {"file_url": blob.public_url}

@app.post("/upload/visita/")
async def upload_foto_visita(onibus_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    # Check if the onibus exists
    onibus = db.query(models.Onibus).filter(models.Onibus.id == onibus_id).first()
    if not onibus:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onibus not found")

    # Upload the file to Firebase Storage
    blob = bucket.blob(f"onibus/{onibus_id}/visita/{file.filename}")
    blob.upload_from_file(file.file, content_type=file.content_type)
    blob.make_public()  # Optionally make the file publicly accessible

    # Update the Onibus record with the new foto_visita URL
    onibus.foto_visita = blob.public_url
    db.commit()

    return {"file_url": blob.public_url}


@app.get("/payments/recent", response_model=List[PaymentResponse])
def get_recent_payments(db: Session = Depends(get_db)):
    # Calculate timestamp 30 minutes ago
    thirty_minutes_ago = datetime.now() - timedelta(minutes=30)

    # Query payments within the last 30 minutes
    recent_payments = db.query(models.Payment).filter(models.Payment.timestamp >= thirty_minutes_ago).all()

    # Convert datetime fields to string format
    for payment in recent_payments:
        payment.timestamp = str(payment.timestamp)

    return recent_payments

@app.get("/payments/status/{payment_id}")
async def get_payment_status(payment_id: str, db: Session = Depends(get_db)):
    try:
        # Fetch payment details from your database
        payment = db.query(models.Payment).filter(models.Payment.payment_id == payment_id).first()
        if not payment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

        # Construct the URL for Mercado Pago API endpoint
        url = f"https://api.mercadopago.com/v1/payments/{payment_id}"

        # Prepare headers with Authorization token
        headers = {
            'Authorization': f'Bearer {os.getenv("MERCADO_PAGO_ACCESS_TOKEN")}',
            'Content-Type': 'application/json',
        }

        # Make GET request to Mercado Pago API using requests library
        response = requests.get(url, headers=headers)

        # Check if the request was successful
        if response.status_code == 200:
            payment_status = response.json()['status']

            # Handle payment confirmation
            if payment_status == 'approved':
                # Perform actions upon payment confirmation
                process_payment_confirmation(payment, db)
                return {"message": "Payment confirmed and processed"}

            elif payment_status == 'pending':
                # Schedule monitoring for payment confirmation
                monitor_payment(payment, db)
                return {"message": "Payment is pending confirmation. Monitoring initiated."}

            else:
                # Payment is not yet confirmed or failed
                return {"message": f"Payment status: {payment_status}"}

        else:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch payment status")

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error fetching payment status from Mercado Pago: {e}")
        raise HTTPException(status_code=500, detail="Error fetching payment status from Mercado Pago")

def monitor_payment(payment: models.Payment, db: Session):
    try:
        if not isinstance(payment, models.Payment):
            raise TypeError("Expected 'payment' to be an instance of models.Payment")

        # Schedule a background task to monitor payment status every minute for 30 minutes
        monitor_thread = Thread(target=monitor_task, args=(payment, db))
        monitor_thread.start()

    except Exception as e:
        print(f"Error in monitor_payment: {e}")

def monitor_task(payment: models.Payment, db: Session):
    try:
        for _ in range(30):  # 30 checks, 1 minute apart
            # Check payment status using the same logic as get_payment_status
            try:
                if not isinstance(payment, models.Payment):
                    raise TypeError("Expected 'payment' to be an instance of models.Payment")

                url = f"https://api.mercadopago.com/v1/payments/{payment.payment_id}"
                headers = {
                    'Authorization': f'Bearer {os.getenv("MERCADO_PAGO_ACCESS_TOKEN")}',
                    'Content-Type': 'application/json',
                }
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    payment_status = response.json()['status']
                    if payment_status == 'approved':
                        # Perform actions upon payment confirmation
                        process_payment_confirmation(payment, db)
                        break  # Exit loop if payment is confirmed
                    elif payment_status != 'pending':
                        break  # Exit loop if payment status is not pending or approved
                else:
                    break  # Exit loop on error fetching status
            except Exception as e:
                print(f"Error monitoring payment {payment.payment_id}: {e}")
            time.sleep(60)  # Wait for 60 seconds before next check
    except Exception as e:
        print(f"Error in monitor_task: {e}")

def process_payment_confirmation(payment: models.Payment, db: Session):
    try:
        # Update payment status to 'approved' in your database
        payment.status = 'approved'
        db.commit()

        # Create reservations in your database
        reservation = models.Reservation(
            id=str(uuid.uuid4()),  # Convert UUID to string for ORM compatibility
            client_id=payment.client_id,
            onibus_id=payment.onibus_id,
            seat_row=payment.seat_row,
            seat_column=payment.seat_column,
        )
        db.add(reservation)
        db.commit()

        # Send confirmation email
        seats = [f"{payment.seat_row},{payment.seat_column}"]
        send_confirmation_email_monitor(payment.client_id, payment.onibus_id, payment.email, seats)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing payment confirmation: {str(e)}")

def send_confirmation_email_monitor(client_id: str, onibus_id: str, email: str, seats: list):
    try:
        # Debugging statements
        print(f"client_id: {client_id}")
        print(f"onibus_id: {onibus_id}")
        print(f"email: {email}")
        print(f"seats: {seats}")

        if not seats or not isinstance(seats, list):
            raise ValueError("Seats list is empty or None or not a list")
        
        subject = "Your Reservation Confirmation"
        body = f"""
        <h1>Reservation Confirmation</h1>
        <p>Dear {client_id},</p>
        <p>Your reservation for the bus with ID {onibus_id} has been confirmed.</p>
        <p>Seats:</p>
        <ul>
        {"".join([f"<li>{seat}</li>" for seat in seats])}
        </ul>
        <p>Thank you for choosing our service!</p>
        """

        print(f"Email body: {body}")  # Debugging statement

        send_email(email, subject, body)
    except Exception as e:
        print(f"Error in send_confirmation_email: {e}")  # Debugging statement
        raise HTTPException(status_code=500, detail=f"Error sending confirmation email: {str(e)}")
        

# Create Database Payment
@app.post("/create_db_payment", response_model=DBPaymentData, status_code=status.HTTP_201_CREATED)
def create_db_payment(payment_data: DBPaymentData, db: Session = Depends(get_db)):
    # Convert approved to boolean
    approved = True if payment_data.approved == "true" else False

    new_payment = models.Payment(
        id=str(uuid.uuid4()),
        client_id=str(payment_data.client_id),
        onibus_id=str(payment_data.onibus_id),
        payment_id=str(payment_data.payment_id),
        email=str(payment_data.email),
        status="pending",
        seat_row=str(payment_data.seat_row),  # Convert to string explicitly if necessary
        seat_column=str(payment_data.seat_column),  # Convert to string explicitly if necessary
        transaction_amount=float(payment_data.transaction_amount),  # Ensure amount is converted appropriately
        approved=approved,
        timestamp=datetime.now()  # No need to convert to string explicitly
    )
    db.add(new_payment)
    db.commit()
    db.refresh(new_payment)

    # Convert fields to strings before returning
    new_payment.email = str(payment_data.email) if payment_data.email else None
    new_payment.timestamp = str(datetime.now())  # Convert timestamp to string if needed
    new_payment.approved = str(approved)  # Convert approved to string

    return new_payment

@app.put("/edit_payment/{payment_id}", response_model=PaymentResponse)
def edit_payment(payment_id: str, payment_update: PaymentUpdate, db: Session = Depends(get_db)):
    payment = db.query(models.Payment).filter(models.Payment.payment_id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    if payment_update.status:
        payment.status = payment_update.status
    if payment_update.amount:
        payment.amount = payment_update.amount

    db.commit()
    db.refresh(payment)
    return payment

@app.delete("/delete_payment/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment(payment_id: str, db: Session = Depends(get_db)):
    payment = db.query(models.Payment).filter(models.Payment.payment_id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    db.delete(payment)
    db.commit()
    return {"message": "Payment deleted successfully"}

@app.post("/approve_payment/{payment_id}", status_code=status.HTTP_200_OK)
def approve_payment(payment_id: str, db: Session = Depends(get_db)):
    payment = db.query(models.Payment).filter(models.Payment.payment_id == payment_id).first()

    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    if payment.status == 'pending':  # Check if payment status is pending
        payment.status = 'approved'  # Change status to approved
        db.commit()  # Commit the change to the database
        return {"message": "Payment approved"}
    else:
        raise HTTPException(status_code=400, detail="Payment not pending or already processed")

@app.get("/get_payment_by_client/{client_id}", response_model=List[PaymentResponse])
def get_payment_by_client(client_id: str, db: Session = Depends(get_db)):
    payments = db.query(models.Payment).filter(models.Payment.client_id == client_id).all()
    if not payments:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No payments found for this client")

    return payments

@app.post("/deny_payment/{payment_id}", status_code=status.HTTP_200_OK)
def deny_payment(payment_id: str, db: Session = Depends(get_db)):
    payment = db.query(models.Payment).filter(models.Payment.payment_id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    payment.status = 'denied'
    db.commit()
    return {"message": "Payment denied"}

#########################################
@app.post("/create_payment", status_code=status.HTTP_201_CREATED)
def create_pix_payment(payment_data: PaymentData, db: Session = Depends(get_db)):
    try:
        payment_request = {
            "transaction_amount": payment_data.transaction_amount,
            "description": "PIX payment",
            "payment_method_id": "pix",
            "payer": {
                "email": payment_data.email
            },
            "notification_url": "https://api.flamengoexcurcoesvrmaracana.online:8000/notification"
        }

        payment_response = sdk.payment().create(payment_request)
        response = payment_response["response"]

        if response["status"] == "pending":
            return {"message": "PIX Payment created", "pix_link": response["point_of_interaction"]["transaction_data"]["ticket_url"]}
        else:
            raise HTTPException(status_code=400, detail="Failed to create PIX payment")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/notification")
async def receive_notification(notification: NotificationData, db: Session = Depends(get_db)):
    payment_id = notification.data['id']

    # Here we would typically call Mercado Libre's API to verify the payment status
    # For the sake of this example, we assume the payment is confirmed if action is `payment.updated`

    if notification.action == 'payment.updated':
        # Find the corresponding reservation and update its status
        reservation = db.query(models.Reservation).filter(models.Reservation.id == payment_id).first()
        if reservation:
            reservation.confirmed = True
            db.commit()
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")

    return {"message": "Notification processed"}

# Example endpoint to check reservation status
@app.get("/reservation_status")
def get_reservation_status(onibus_id: str, email: str, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.email == email).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    reservation = db.query(models.Reservation).filter(models.Reservation.onibus_id == onibus_id, models.Reservation.client_id == client.id).first()
    if not reservation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")

    return {"confirmed": reservation.confirmed}


########## if reservation is confirmed, call endpoint too send email with confirmation##################
#### RESERVATION_CONFIRMATION ###################



##################### CREATE CLIENTE #####
@app.post("/clients/", response_model=ClientBase)
def create_client(client: ClientBase, db: Session = Depends(get_db)):
    db_client = models.Client(**client.model_dump())
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client


########### ATUALIZAR CLIENTE###############
@app.put("/clients/{client_id}", response_model=ClientBase)
def update_client(client_id: str, client: ClientBase, db: Session = Depends(get_db)):
    db_client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not db_client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    for field, value in client.dict(exclude_unset=True).items():
        setattr(db_client, field, value)

    db.commit()
    db.refresh(db_client)
    return db_client

####### APAGAR CLIENTE #######
@app.delete("/clients/{client_id}")
def delete_client(client_id: str, db: Session = Depends(get_db)):
    db_client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not db_client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    db.delete(db_client)
    db.commit()
    return {"message": "Client deleted successfully"}



####### PEGAR TODOS OS CLIENTES #####
@app.get("/clients/", response_model=List[ClientBase])
def get_all_clients(db: Session = Depends(get_db)):
    return db.query(models.Client).all()



##### PEGAR CLIENTE POR ID

@app.get("/clients/{client_id}", response_model=ClientBase)
def get_client_by_id(client_id: str, db: Session = Depends(get_db)):
    db_client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not db_client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    return db_client



##########CREATE ONIBUS############################
@app.post("/onibus/", response_model=OnibusBase)
def create_onibus(onibus: OnibusBase, db: Session = Depends(get_db)):
    db_onibus = models.Onibus(**onibus.model_dump())
    db.add(db_onibus)
    db.commit()
    db.refresh(db_onibus)
    return db_onibus

############UPDATE ONIBUS ####################
@app.put("/onibus/{onibus_id}", response_model=OnibusBase)
def update_onibus(onibus_id: str, onibus: OnibusBase, db: Session = Depends(get_db)):
    db_onibus = db.query(models.Onibus).filter(models.Onibus.id == onibus_id).first()
    if not db_onibus:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onibus not found")

    for field, value in onibus.model_dump(exclude_unset=True).items():
        setattr(db_onibus, field, value)

    db.commit()
    db.refresh(db_onibus)
    return db_onibus

##############DELETE ONIBUS ############################
@app.delete("/onibus/{onibus_id}")
def delete_onibus(onibus_id: str, db: Session = Depends(get_db)):
    db_onibus = db.query(models.Onibus).filter(models.Onibus.id == onibus_id).first()
    if not db_onibus:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onibus not found")

    db.delete(db_onibus)
    db.commit()
    return {"message": "Onibus deleted successfully"}


################ GET ALL ONIBUS ################
@app.get("/onibus/", response_model=List[OnibusBase])
def get_all_onibus(db: Session = Depends(get_db)):
    return db.query(models.Onibus).all()


################## GET ONIBUS BY ID
@app.get("/onibus/{onibus_id}", response_model=OnibusBase)
def get_onibus_by_id(onibus_id: str, db: Session = Depends(get_db)):
    db_onibus = db.query(models.Onibus).filter(models.Onibus.id == onibus_id).first()
    if not db_onibus:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onibus not found")

    return db_onibus

###############RESERVE SYSTEM##############################
@app.post("/reserve/{onibus_id}", status_code=status.HTTP_201_CREATED)
def create_reserve(onibus_id: str, request: ReserveRequest, db: Session = Depends(get_db)):
    onibus = db.query(models.Onibus).filter(models.Onibus.id == onibus_id).first()
    if not onibus:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onibus not found")

    for seat in request.seats:
        reservation = models.Reservation(
            id=str(uuid.uuid4()),
            client_id=request.client_id,
            onibus_id=onibus_id,
            seat_row=seat.row,
            seat_column=seat.column,
            timestamp=datetime.utcnow()
        )
        db.add(reservation)

    onibus.vagas -= len(request.seats)
    db.commit()

    return {"message": "Reservation created successfully"}

################################UPDATE RESERVE###################
@app.put("/reserve/{reservation_id}", status_code=status.HTTP_200_OK)
def update_reserve(reservation_id: str, request: ReserveRequest, db: Session = Depends(get_db)):
    reservation = db.query(models.Reservation).filter(models.Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")

    reservation.client_id = request.client_id
    reservation.seat_row = request.seats[0].row
    reservation.seat_column = request.seats[0].column

    db.commit()
    db.refresh(reservation)

    return reservation


####################DELETE RESERVE##############################
@app.delete("/reserve/{reservation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reserve(reservation_id: str, db: Session = Depends(get_db)):
    reservation = db.query(models.Reservation).filter(models.Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")

    onibus = db.query(models.Onibus).filter(models.Onibus.id == reservation.onibus_id).first()
    onibus.vagas += 1

    db.delete(reservation)
    db.commit()
    return {"message": "Reservation deleted successfully"}

################ GET RESERVE BY BUS ID #####################
@app.get("/reserve/onibus/{onibus_id}/seats", response_model=List[Seat])
def get_reserved_seats(onibus_id: str, db: Session = Depends(get_db)):
    reservations = db.query(models.Reservation).filter(models.Reservation.onibus_id == onibus_id).all()
    reserved_seats = [{"row": reservation.seat_row, "column": reservation.seat_column} for reservation in reservations]
    return reserved_seats
########################GET ALL RESERVES##########################
@app.get("/reserve/", response_model=List[ReservationResponse], status_code=status.HTTP_200_OK)
def get_all_reservations(db: Session = Depends(get_db)):
    reservations = db.query(models.Reservation).all()
    # Convert timestamp to string before returning
    response = []
    for reservation in reservations:
        reservation_dict = reservation.__dict__.copy()
        reservation_dict['timestamp'] = reservation.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        response.append(ReservationResponse(**reservation_dict))
    return response


########################GET RESERVATION BY ID#####################
@app.get("/reserve/{reservation_id}", response_model=ReservationResponse, status_code=status.HTTP_200_OK)
def get_reserve_by_id(reservation_id: str, db: Session = Depends(get_db)):
    reservation = db.query(models.Reservation).filter(models.Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")

    # Convert timestamp to string before returning
    reservation_dict = reservation.__dict__.copy()
    reservation_dict['timestamp'] = reservation.timestamp.strftime('%Y-%m-%d %H:%M:%S')

    return ReservationResponse(**reservation_dict)



#create onibus

#update onibus
#delete onibus
#get all onibus
#get onibus by ID
#get empty vagas onibus/ sistema de vagas
#get client viagens
#create cliente
#update client
#add viagen client
#delete cliente
#pegar comprovate por cliente
#pegar passagen por cliente





