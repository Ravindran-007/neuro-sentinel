import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from confluent_kafka import Producer, KafkaError, KafkaException

logger = logging.getLogger("NeuroSentinel-Kafka")

# ─────────────────────────────────────────────────────────────
# KAFKA CONFIGURATION
# ─────────────────────────────────────────────────────────────

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_AGENT_EVENTS = os.getenv("KAFKA_TOPIC_AGENT_EVENTS", "agent-events")
KAFKA_TOPIC_ANOMALIES = os.getenv("KAFKA_TOPIC_ANOMALIES", "anomaly-detections")
KAFKA_TOPIC_ALERTS = os.getenv("KAFKA_TOPIC_ALERTS", "security-alerts")
KAFKA_TOPIC_ROLLBACKS = os.getenv("KAFKA_TOPIC_ROLLBACKS", "checkpoint-rollbacks")


class KafkaEventProducer:
    """
    Kafka producer for NeuroSentinel events using confluent-kafka.
    """
    
    def __init__(self, bootstrap_servers: Optional[str] = None):
        self.bootstrap_servers = bootstrap_servers or KAFKA_BOOTSTRAP_SERVERS
        self.producer = None
        self.initialized = False
        
        try:
            conf = {
                'bootstrap.servers': self.bootstrap_servers,
                'acks': 'all',
                'retries': 3,
                'client.id': 'neurosentinel-producer'
            }
            self.producer = Producer(conf)
            self.initialized = True
            logger.info(f"✅ Kafka producer connected to {self.bootstrap_servers}")
        except Exception as e:
            logger.warning(f"⚠️ Kafka unavailable ({e}). Using mock producer.")
            self.initialized = False
    
    def produce_event(self, topic: str, event_type: str, data: Dict[str, Any]) -> bool:
        """Produce an event to Kafka."""
        if not self.initialized:
            logger.debug(f"📝 Mock event: {event_type} -> {topic}")
            return False
        
        try:
            event = {
                "event_id": f"{event_type}_{int(datetime.now().timestamp() * 1000)}",
                "event_type": event_type,
                "timestamp": datetime.now().isoformat(),
                "data": data
            }
            
            # Produce message
            self.producer.produce(
                topic,
                value=json.dumps(event).encode('utf-8'),
                callback=self._delivery_report
            )
            self.producer.flush()
            
            logger.info(f"✅ Event produced: {event_type} -> {topic}")
            return True
            
        except KafkaException as e:
            logger.error(f"❌ Kafka error: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to produce event: {e}")
            return False
    
    def _delivery_report(self, err, msg):
        """Delivery report callback."""
        if err is not None:
            logger.error(f"❌ Message delivery failed: {err}")
        else:
            logger.debug(f"✅ Message delivered to {msg.topic()} [{msg.partition()}]")
    
    def produce_detection(self, detection_result: Dict[str, Any]) -> bool:
        return self.produce_event(KAFKA_TOPIC_AGENT_EVENTS, "detection", detection_result)
    
    def produce_anomaly(self, anomaly_data: Dict[str, Any]) -> bool:
        return self.produce_event(KAFKA_TOPIC_ANOMALIES, "anomaly", anomaly_data)
    
    def produce_alert(self, alert_data: Dict[str, Any]) -> bool:
        return self.produce_event(KAFKA_TOPIC_ALERTS, "alert", alert_data)
    
    def produce_rollback(self, rollback_data: Dict[str, Any]) -> bool:
        return self.produce_event(KAFKA_TOPIC_ROLLBACKS, "rollback", rollback_data)
    
    def close(self):
        if self.producer:
            self.producer.flush()
            logger.info("✅ Kafka producer closed")


# Singleton instance
kafka_producer = KafkaEventProducer()
