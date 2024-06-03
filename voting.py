import random  # For generating random data
import time  # For time-related functions
from datetime import datetime  # For handling date and time

import psycopg2  # PostgreSQL database adapter for Python
import simplejson as json  # For JSON manipulation
from confluent_kafka import Consumer, KafkaException, KafkaError, SerializingProducer  # Kafka components

from main import delivery_report  # Import delivery_report function from main script

# Kafka configuration
conf = {
    'bootstrap.servers': 'localhost:9092',  # Kafka broker
}

# Kafka consumer configuration
consumer = Consumer(conf | {
    'group.id': 'voting-group',  # Consumer group ID
    'auto.offset.reset': 'earliest',  # Reset offset to earliest
    'enable.auto.commit': False  # Disable auto commit of offsets
})

# Kafka producer configuration
producer = SerializingProducer(conf)

# Function to consume messages from 'candidates_topic'
def consume_messages():
    result = []
    consumer.subscribe(['candidates_topic'])  # Subscribe to 'candidates_topic'
    try:
        while True:
            msg = consumer.poll(timeout=1.0)  # Poll for messages
            if msg is None:
                continue  # No message received, continue polling
            elif msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue  # End of partition reached, continue polling
                else:
                    print(msg.error())  # Print error message
                    break
            else:
                result.append(json.loads(msg.value().decode('utf-8')))  # Decode message value and append to result
                if len(result) == 3:
                    return result  # Return result when 3 messages are consumed

    except KafkaException as e:
        print(e)  # Print exception

# Main execution block
if __name__ == "__main__":
    # Connect to PostgreSQL database
    conn = psycopg2.connect("host=localhost dbname=election_db user=postgres password=postgres port=5433")
    cur = conn.cursor()

    # Fetch candidates from the database
    candidates_query = cur.execute("""
        SELECT row_to_json(col)
        FROM (
            SELECT * FROM candidates
        ) col;
    """)
    candidates = cur.fetchall()
    candidates = [candidate[0] for candidate in candidates]  # Extract candidate data
    if len(candidates) == 0:
        raise Exception("No candidates found in database")  # Raise exception if no candidates found
    else:
        print(candidates)  # Print candidates

    # Subscribe to 'voters_topic'
    consumer.subscribe(['voters_topic'])
    try:
        while True:
            msg = consumer.poll(timeout=1.0)  # Poll for messages
            if msg is None:
                continue  # No message received, continue polling
            elif msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue  # End of partition reached, continue polling
                else:
                    print(msg.error())  # Print error message
                    break
            else:
                voter = json.loads(msg.value().decode('utf-8'))  # Decode message value
                chosen_candidate = random.choice(candidates)  # Randomly choose a candidate
                vote = voter | chosen_candidate | {
                    "voting_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),  # Current UTC time
                    "vote": 1  # Vote value
                }

                try:
                    print("User {} is voting for candidate: {}".format(vote['voter_id'], vote['candidate_id']))
                    # Insert vote into 'votes' table
                    cur.execute("""
                            INSERT INTO votes (voter_id, candidate_id, voting_time)
                            VALUES (%s, %s, %s)
                        """, (vote['voter_id'], vote['candidate_id'], vote['voting_time']))

                    conn.commit()  # Commit the transaction

                    # Produce vote to 'votes_topic'
                    producer.produce(
                        'votes_topic',
                        key=vote["voter_id"],
                        value=json.dumps(vote),
                        on_delivery=delivery_report
                    )
                    producer.poll(0)  # Poll producer events
                except Exception as e:
                    print("Error: {}".format(e))  # Print exception message
                    continue
            time.sleep(0.5)  # Sleep for 0.5 seconds before next poll
    except KafkaException as e:
        print(e)  # Print Kafka exception