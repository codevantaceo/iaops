"""
Simple test for the multi-agent system.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from indestructibleautoops.agents import (
    AgentCapability,
    AgentMessage,
    MessageType,
)


@pytest.mark.asyncio
async def test_agent_basics():
    """Test basic agent functionality."""
    print("Testing Multi-Agent System Basics")
    print("=" * 60)

    # Test 1: AgentCapability
    print("\n1. Testing AgentCapability...")
    cap = AgentCapability(
        name="test_capability",
        description="Test capability",
        input_types=["input"],
        output_types=["output"],
    )

    assert cap.name == "test_capability"
    assert cap.can_handle("input")
    assert not cap.can_handle("other")
    print("   ✓ AgentCapability works correctly")

    # Test 2: AgentMessage
    print("\n2. Testing AgentMessage...")
    msg = AgentMessage(
        msg_type=MessageType.TASK_ASSIGN,
        sender_id="agent1",
        recipient_id="agent2",
        payload={"task": "test"},
    )

    assert msg.msg_type == MessageType.TASK_ASSIGN
    assert msg.sender_id == "agent1"
    assert msg.recipient_id == "agent2"
    print("   ✓ AgentMessage works correctly")

    # Test 3: Message serialization
    print("\n3. Testing message serialization...")
    msg_dict = msg.to_dict()
    msg2 = AgentMessage.from_dict(msg_dict)

    assert msg2.msg_type == msg.msg_type
    assert msg2.sender_id == msg.sender_id
    assert msg2.recipient_id == msg.recipient_id
    assert msg2.payload == msg.payload
    print("   ✓ Message serialization works correctly")

    # Test 4: MessageType enum
    print("\n4. Testing MessageType enum...")
    assert MessageType.TASK_ASSIGN.value == "task_assign"
    assert MessageType.TASK_COMPLETE.value == "task_complete"
    assert MessageType.HEARTBEAT.value == "heartbeat"
    print("   ✓ MessageType enum works correctly")

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_agent_basics())
