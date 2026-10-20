import firebase_admin
from firebase_admin import credentials, firestore

cred_a = credentials.Certificate(r"firebase_credentials_c.json")
app_a = firebase_admin.initialize_app(cred_a, name='ProyectoA')
db_a = firestore.client(app=app_a)

cred_b = credentials.Certificate(r"firebase_credentials_a.json")
app_b = firebase_admin.initialize_app(cred_b, name='ProyectoB')
db_b = firestore.client(app=app_b)

print("Iniciando clonación de respuestas de A -> B...")

respuestas_a = db_a.collection("respuestas").stream()

batch = db_b.batch()
contador = 0

for doc in respuestas_a:
    ref_b = db_b.collection("respuestas").document(doc.id)
    batch.set(ref_b, doc.to_dict())
    
    contador += 1
    if contador % 400 == 0:
        batch.commit()
        batch = db_b.batch()

if contador % 400 != 0:
    batch.commit()

print(f"¡Migración exitosa! Se copiaron {contador} respuestas al Proyecto B.")