"""
Example usage of the Multi-Agent Orchestration System.

This script demonstrates how to use the IndestructibleAutoOps
multi-agent system for project analysis, repair planning, and execution.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from indestructibleautoops.agents.orchestrator import (
    create_orchestrator,
)
from indestructibleautoops.agents.policy_engine import Policy, PolicySeverity, PolicyType


async def main():
    """Main example function."""

    # Get project root (current directory)
    project_root = str(Path(__file__).parent.parent)
    state_dir = str(Path(project_root) / ".iaops_state")

    print("=" * 60)
    print("IndestructibleAutoOps Multi-Agent Orchestration Demo")
    print("=" * 60)
    print(f"Project Root: {project_root}")
    print(f"State Directory: {state_dir}")
    print()

    # Create orchestrator
    print("Creating orchestrator...")
    try:
        orchestrator = await create_orchestrator(
            project_root=project_root,
            state_dir=state_dir,
            max_concurrent_tasks=5,
            enable_observability=True,
            enable_policy_enforcement=True,
        )
    except Exception as e:
        print(f"ERROR: Failed to create orchestrator: {e}")
        import traceback

        traceback.print_exc()
        return

    print("Orchestrator initialized successfully!")
    print()

    # Show orchestrator stats
    print("Orchestrator Statistics:")
    print("-" * 60)
    stats = orchestrator.get_orchestrator_stats()
    print(f"  Registry: {stats['registry']['total_agents']} agents registered")
    print(f"  Lifecycle: {stats['lifecycle']['total_instances']} instances running")
    print(f"  Communication: {stats['communication']['registered_agents']} agents on bus")
    print(f"  Policies: {stats['policy_engine']['total_policies']} policies loaded")
    print()

    # Add custom policy
    print("Adding custom policy...")
    custom_policy = Policy(
        name="max_file_size",
        description="Prevent files larger than 10MB",
        policy_type=PolicyType.SECURITY,
        severity=PolicySeverity.WARNING,
        conditions={
            "file_size": {"lte": 10 * 1024 * 1024},
        },
        actions=["log"],
    )
    orchestrator.add_policy(custom_policy)
    print(f"  Policy '{custom_policy.name}' added")
    print()

    # Analyze project
    print("Analyzing project...")
    print("-" * 60)
    analysis = await orchestrator.analyze_project()

    if analysis["success"]:
        snapshot = analysis["snapshot"]
        print(f"  Snapshot ID: {snapshot['snapshot_id']}")
        print(f"  Files scanned: {snapshot['file_count']}")
        print(f"  Total size: {snapshot['total_size']} bytes")

        if analysis.get("risk_findings"):
            findings = analysis["risk_findings"]
            print(f"  Risks found: {findings['total_risks']}")
            if findings["by_severity"]:
                print(f"    Critical: {findings['by_severity'].get('critical', 0)}")
                print(f"    High: {findings['by_severity'].get('high', 0)}")
                print(f"    Medium: {findings['by_severity'].get('medium', 0)}")
                print(f"    Low: {findings['by_severity'].get('low', 0)}")

        if analysis.get("policy_evaluation"):
            policy_eval = analysis["policy_evaluation"]
            print(f"  Policy evaluation: {'PASSED' if policy_eval.get('passed') else 'FAILED'}")
            violations = policy_eval.get("violations", [])
            if violations:
                print(f"  Policy violations: {len(violations)}")
    else:
        print(f"  Analysis failed: {analysis.get('error')}")

    print()

    # Create repair plan
    print("Creating repair plan...")
    print("-" * 60)
    repair_plan_result = await orchestrator.create_repair_plan()

    if repair_plan_result["success"]:
        plan = repair_plan_result["repair_plan"]["repair_plan"]
        print(f"  Plan ID: {plan['plan_id']}")
        print(f"  Issues found: {len(plan.get('issues_found', []))}")
        print(f"  Steps to execute: {len(plan.get('steps', []))}")
        print(f"  Estimated duration: {plan.get('estimated_duration', 0):.1f}s")

        # Show first few steps
        steps = plan.get("steps", [])
        if steps:
            print("\n  First few steps:")
            for i, step in enumerate(steps[:5]):
                print(
                    f"    {i + 1}. [{step.get('priority', 'unknown')}] {step.get('name', 'unnamed')}"
                )
            if len(steps) > 5:
                print(f"    ... and {len(steps) - 5} more steps")
    else:
        print(f"  Repair plan creation failed: {repair_plan_result.get('error')}")

    print()

    # Generate CI configuration
    print("Generating CI configuration...")
    print("-" * 60)
    ci_result = await orchestrator.generate_ci_config(provider="github")

    if ci_result["success"]:
        patch_set = ci_result["ci_config"]["patch_set"]
        print(f"  Patch Set ID: {patch_set['patch_id']}")
        print(f"  Provider: {patch_set['provider']}")
        print(f"  Patches generated: {len(patch_set.get('patches', []))}")

        patches = patch_set.get("patches", [])
        for patch in patches:
            print(f"    - {patch.get('file_path')}")
    else:
        print(f"  CI config generation failed: {ci_result.get('error')}")

    print()

    # Execute a custom pipeline
    print("Executing custom pipeline...")
    print("-" * 60)

    pipeline_steps = [
        {
            "type": "file_scan",
            "payload": {"project_root": project_root},
            "required_capabilities": ["file_scan"],
        },
        {
            "type": "analyze_risks",
            "payload": {"project_snapshot": {"project_root": project_root}},
            "required_capabilities": ["analyze_risks"],
        },
    ]

    pipeline_result = await orchestrator.execute_pipeline(pipeline_steps)

    print(f"  Success: {pipeline_result.success}")
    print(f"  Tasks completed: {pipeline_result.tasks_completed}")
    print(f"  Tasks failed: {pipeline_result.tasks_failed}")
    print(f"  Total duration: {pipeline_result.total_duration:.2f}s")

    if pipeline_result.errors:
        print("\n  Errors:")
        for error in pipeline_result.errors:
            print(f"    - {error}")

    print()

    # Final statistics
    print("Final Statistics:")
    print("-" * 60)
    final_stats = orchestrator.get_orchestrator_stats()
    print(f"  Total tasks processed: {final_stats['coordinator']['total_tasks']}")
    print(f"  Tasks completed: {final_stats['coordinator']['completed_tasks']}")
    print(f"  Tasks running: {final_stats['coordinator']['running_tasks']}")
    print()

    # Shutdown
    print("Shutting down orchestrator...")
    await orchestrator.shutdown()
    print("Orchestrator shut down successfully!")
    print()

    print("=" * 60)
    print("Demo completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
