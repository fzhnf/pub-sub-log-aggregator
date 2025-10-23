#!/bin/bash
# test_docker.sh

echo "Testing Docker deployment..."

# Health check
echo "1. Health check:"
curl -s http://localhost:8080/health | jq

# Send event
echo -e "\n2. Sending event:"
curl -s -X POST http://localhost:8080/publish \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "topic": "docker.test",
      "event_id": "test-001",
      "timestamp": "2025-10-23T10:00:00Z",
      "source": "test-script",
      "payload": {"message": "Docker test"}
    }]
  }' | jq

sleep 1

# Check stats
echo -e "\n3. Stats after 1 event:"
curl -s http://localhost:8080/stats | jq

# Send duplicate
echo -e "\n4. Sending duplicate:"
curl -s -X POST http://localhost:8080/publish \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "topic": "docker.test",
      "event_id": "test-001",
      "timestamp": "2025-10-23T10:00:01Z",
      "source": "test-script",
      "payload": {"message": "Duplicate"}
    }]
  }' | jq

sleep 1

# Check stats again
echo -e "\n5. Stats after duplicate:"
curl -s http://localhost:8080/stats | jq

echo -e "\n✅ Docker test complete!"
