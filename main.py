import psycopg2  # PostgreSQL database adapter for Python
import requests  # For making HTTP requests
import random  # For generating random data
import simplejson as json  # For JSON manipulation
from confluent_kafka import SerializingProducer  # Kafka producer for sending messages

# Constants
BASE_URL = 'https://randomuser.me/api/?nat=us'  # Base URL for the random user API
PARTIES = ["Gangster Party", "Anime Party", "Asleep Party"]  # List of party affiliations
random.seed(1)  # Seed for random number generation

# Function to generate candidate data
def generate_candidate_data(candidate_number, total_parties):
    # Fetch random user data based on gender
    response = requests.get(BASE_URL + '&gender=' + ('female' if candidate_number % 2 == 1 else 'male'))
    if response.status_code == 200:
        user_data = response.json()['results'][0]

        # Return candidate data as a dictionary
        return {
            "candidate_id": user_data['login']['uuid'],
            "candidate_name": f"{user_data['name']['first']} {user_data['name']['last']}",
            "party_affiliation": PARTIES[candidate_number % total_parties],
            "biography": "A brief bio of the candidate.",
            "campaign_platform": "Key campaign promises or platform.",
            "photo_url": user_data['picture']['large']
        }
    else:
        return "Error fetching candidate data"

# Function to generate voter data
def generate_voter_data():
    # Fetch random user data
    response = requests.get(BASE_URL)
    if response.status_code == 200:
        user_data = response.json()['results'][0]

        # Return voter data as a dictionary
        return {
            "voter_id": user_data['login']['uuid'],
            "voter_name": f"{user_data['name']['first']} {user_data['name']['last']}",
            "date_of_birth": user_data['dob']['date'],
            "gender": user_data['gender'],
            "nationality": user_data['nat'],
            "registration_number": user_data['login']['username'],
            "address": {
                "street": f"{user_data['location']['street']['number']} {user_data['location']['street']['name']}",
                "city": user_data['location']['city'],
                "state": user_data['location']['state'],
                "country": user_data['location']['country'],
                "postcode": user_data['location']['postcode']
            },
            "email": user_data['email'],
            "phone_number": user_data['phone'],
            "picture": user_data['picture']['large'],
            "registered_date": user_data['registered']['date'],
            "registered_age": user_data['registered']['age']
        }
    else:
        return "Error fetching voter data"

# Function to insert voter data into the PostgreSQL database
def insert_voters(conn, cur, voter):
    cur.execute("""
                        INSERT INTO voters (voter_id, voter_name, date_of_birth, gender, nationality, registration_number, address_street, address_city, address_state, address_country, address_postcode, email, phone_number, picture, registered_date, registered_age)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s,%s,%s,%s,%s,%s)
                        """,
                (voter["voter_id"], voter['voter_name'], voter['date_of_birth'], voter['gender'],
                 voter['nationality'], voter['registration_number'], voter['address']['street'],
                 voter['address']['city'], voter['address']['state'], voter['address']['country'],
                 voter['address']['postcode'], voter['email'], voter['phone_number'],
                 voter['picture'], voter['registered_date'], voter['registered_age'])
                )
    conn.commit()

# Callback function for Kafka delivery reports
def delivery_report(err, msg):
    if err is not None:
        print(f'Message delivery failed: {err}')
    else:
        print(f'Message delivered to {msg.topic()} [{msg.partition()}]')

# Kafka Topics
voters_topic = 'voters_topic'
candidates_topic = 'candidates_topic'

# Function to create necessary tables in the PostgreSQL database
def create_tables(conn, cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            candidate_id VARCHAR(255) PRIMARY KEY,
            candidate_name VARCHAR(255),
            party_affiliation VARCHAR(255),
            biography TEXT,
            campaign_platform TEXT,
            photo_url TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS voters (
            voter_id VARCHAR(255) PRIMARY KEY,
            voter_name VARCHAR(255),
            date_of_birth VARCHAR(255),
            gender VARCHAR(255),
            nationality VARCHAR(255),
            registration_number VARCHAR(255),
            address_street VARCHAR(255),
            address_city VARCHAR(255),
            address_state VARCHAR(255),
            address_country VARCHAR(255),
            address_postcode VARCHAR(255),
            email VARCHAR(255),
            phone_number VARCHAR(255),
            picture TEXT,
            registered_date VARCHAR(255),
            registered_age INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            voter_id VARCHAR(255) UNIQUE,
            candidate_id VARCHAR(255),
            voting_time TIMESTAMP,
            vote int DEFAULT 1,
            PRIMARY KEY (voter_id, candidate_id)
        )
    """)

    conn.commit()

# Main execution block
if __name__ == "__main__":
    producer = SerializingProducer({'bootstrap.servers': 'localhost:9092', })
    try:
        conn = psycopg2.connect("host=localhost dbname=election_db user=postgres password=postgres port=5433")

        cur = conn.cursor()

        create_tables(conn, cur)

        cur.execute("""
        SELECT * FROM candidates
        """)
        candidates = cur.fetchall()

        # Insert candidate data if the candidates table is empty
        if len(candidates) == 0:
            for i in range(3):
                candidate = generate_candidate_data(i, 3)
                cur.execute("""
                            INSERT INTO candidates (candidate_id, candidate_name, party_affiliation, biography, campaign_platform, photo_url)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                    candidate['candidate_id'], candidate['candidate_name'], candidate['party_affiliation'], candidate['biography'],
                    candidate['campaign_platform'], candidate['photo_url']))
                conn.commit()

        # Generate and insert voter data, then produce it to Kafka
        for i in range(500):
            voter_data = generate_voter_data()
            insert_voters(conn, cur, voter_data)

            producer.produce(
                voters_topic,
                key=voter_data["voter_id"],
                value=json.dumps(voter_data),
                on_delivery=delivery_report
            )

            print('Produced voter {}, data: {}'.format(i, voter_data))
        producer.flush()

    except Exception as e:
        print(e)
