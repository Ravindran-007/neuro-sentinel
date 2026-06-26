import json
import os
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from confluent_kafka import Consumer, KafkaError, KafkaException

logger = logging.getLogger("NeuroSentinel-Kafka")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "neurosentinel-consumer")
KAFKA_DLQ_TOPIC = os.getenv("KAFKA_DLQ_TOPIC", "dead-letter-queue")


class KafkaEventConsumer:
    """Kafka consumer with Dead Letter Queue support."""
    
    def __init__(self, topics: list, group_id: Optional[str] = None, bootstrap_servers: Optional[str] = None):
        self.bootstrap_servers = bootstrap_servers or KAFKA_BOOTSTRAP_SERVERS
        self.group_id = group_id or KAFKA_GROUP_ID
        self.topics = topics
        self.consumer = None
        self.initialized = False
        self.handlers = {}
        
        try:
            conf = {
                'bootstrap.servers': self.bootstrap_servers,
                'group.id': self.group_id,
                'auto.offset.reset': 'earliest',
                'enable.auto.commit': False,
                'client.id': 'neurosentinel-consumer'
            }
            self.consumer = Consumer(conf)
            self.consumer.subscribe(topics)
            self.initialized = True
            logger.info(f"✅ Kafka consumer connected to {self.bootstrap_servers}")
            logger.info(f"📋 Subscribed to topics: {topics}")
        except Exception as e:
            logger.warning(f"⚠️ Kafka unavailable ({e}). Using mock consumer.")
            self.initialized = False
    
    def register_handler(self, event_type: str, handler: Callable):
        self.handlers[event_type] = handler
        logger.info(f"📋 Handler registered for: {event_type}")
    
    def process_event(self, event: Dict[str, Any]) -> bool:
        event_type = event.get('event_type', 'unknown')
        if event_type in self.handlers:
            try:
                self.handlers[event_type](event)
                return True
            except Exception as e:
                logger.error(f"❌ Handler failed for {event_type}: {e}")
                return False
        return False
    
    def consume_events(self, timeout: float = 1.0):
        if not self.initialized:
            return
        
        try:
            msg = self.consumer.poll(timeout)
            if msg is None:
                return
            
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    return
                else:
                    logger.error(f"❌ Consumer error: {msg.error()}")
                    return
            
            event = json.loads(msg.value().decode('utf-8'))
            if self.process_event(event):
                self.consumer.commit()
            else:
                self._send_to_dlq(event, "Processing failed")
                
        except Exception as e:
            logger.error(f"❌ Consumer error: {e}")
    
    def _send_to_dlq(self, event: Dict[str, Any], reason: str):
        from core.kafka_producer import kafka_producer
        dlq_event = {
            "original_event": event,
            "failure_reason": reason,
            "timestamp": datetime.now().isoformat()
        }
        kafka_producer.produce_event(KAFKA_DLQ_TOPIC, "dlq_event", dlq_event)
        logger.warning(f"📋 Event sent to DLQ: {reason}")
    
    def close(self):
        if self.consumer:
            self.consumer.close()


# Default handlers
def handle_detection(event: Dict[str, Any]):
    data = event.get('data', {})
    logger.info(f"📊 Detection: {data.get('agent_role')} - {data.get('overall_status')}")

def handle_anomaly(event: Dict[str, Any]):
    data = event.get('data', {})
    logger.warning(f"🚨 ANOMALY: {data.get('agent_role')} - Score: {data.get('structural_score')}")

def handle_alert(event: Dict[str, Any]):
    data = event.get('data', {})
    logger.critical(f"🔥 ALERT: {data.get('message')}")

def handle_rollback(event: Dict[str, Any]):
    data = event.get('data', {})
    logger.info(f"🔄 ROLLBACK: {data.get('agent_role')}")
