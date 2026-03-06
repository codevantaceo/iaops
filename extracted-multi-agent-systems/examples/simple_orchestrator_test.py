"""
Simple test for the orchestrator without spawning all agents.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from indestructibleautoops.agents import (
    AgentCommunicationBus,
    AgentCoordinator,
    AgentLifecycle,
    AgentRegistry,
    Policy,
    PolicyEngine,
    PolicySeverity,
    PolicyType,
)


@pytest.mark.asyncio
async def test_orchestrator_components():
    """Test orchestrator components individually."""
    print("Testing Orchestrator Components")
    print("=" * 60)

    # Test 1: AgentRegistry
    print("\n1. Testing AgentRegistry...")
    registry = AgentRegistry()
    print("   ✓ AgentRegistry created")

    # Test 2: AgentCommunicationBus
    print("\n2. Testing AgentCommunicationBus...")
    comm = AgentCommunicationBus()
    comm.start_delivery()
    print("   ✓ AgentCommunicationBus created and started")

    # Test 3: AgentCoordinator
    print("\n3. Testing AgentCoordinator...")
    coordinator = AgentCoordinator(registry, comm)
    coordinator.start()
    print("   ✓ AgentCoordinator created and started")

    # Test 4: AgentLifecycle
    print("\n4. Testing AgentLifecycle...")
    AgentLifecycle(registry, comm)
    print("   ✓ AgentLifecycle created")

    # Test 5: PolicyEngine
    print("\n5. Testing PolicyEngine...")
    policy_engine = PolicyEngine()

    # Add a test policy
    test_policy = Policy(
        name="test_policy",
        description="Test policy",
        policy_type=PolicyType.SECURITY,
        severity=PolicySeverity.WARNING,
        conditions={"test": {"eq": True}},
        actions=["log"],
    )
    policy_engine.add_policy(test_policy)
    print("   ✓ PolicyEngine created and policy added")

    # Test 6: Policy evaluation
    print("\n6. Testing policy evaluation...")
    passed, violations = policy_engine.evaluate_action(
        agent_id="test_agent",
        action="test_action",
        context={"test": True},
        agent_tags=[],
        block_on_critical=False,
    )
    assert passed, "Policy should pass"
    print(f"   ✓ Policy evaluation passed (violations: {len(violations)})")

    # Test 7: Communication message sending
    print("\n7. Testing communication message...")
    from indestructibleautoops.agents import AgentMessage, MessageType

    # Register a test agent
    comm.register_agent("test_agent")

    # Send a message
    msg = AgentMessage(
        msg_type=MessageType.HEARTBEAT,
        sender_id="sender",
        recipient_id="test_agent",
        payload={},
    )
    sent = comm.send(msg)
    assert sent, "Message should be sent"
    print("   ✓ Communication message sent successfully")

    # Test 8: Coordinator stats
    print("\n8. Testing coordinator statistics...")
    stats = coordinator.get_coordinator_stats()
    assert "total_tasks" in stats
    assert "running_tasks" in stats
    print(f"   ✓ Coordinator stats retrieved: {stats}")

    # Test 9: Registry stats
    print("\n9. Testing registry statistics...")
    stats = registry.get_registry_stats()
    assert "total_agents" in stats
    print(f"   ✓ Registry stats retrieved: {stats}")

    # Test 10: Communication stats
    print("\n10. Testing communication statistics...")
    stats = comm.get_bus_stats()
    assert "registered_agents" in stats
    print(f"   ✓ Communication stats retrieved: {stats}")

    # Cleanup
    print("\n11. Cleaning up...")
    coordinator.stop()
    comm.stop_delivery()
    print("   ✓ Coordinator and communication stopped")

    print("\n" + "=" * 60)
    print("All orchestrator component tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_orchestrator_components())
