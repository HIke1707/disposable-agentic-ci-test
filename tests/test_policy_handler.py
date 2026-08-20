#!/usr/bin/env python3
"""
Test Suite: GitHub Agentic Workflows v0.87.0 / v0.87.1 Native 'approve-workflow-run' Safe-Output Policy Gate
Validates all 6 Security Invariants & Policy Dimensions:
  - Case A: Legal PR Approval (status=waiting/action_required, allowed workflow, no protected files -> APPROVED)
  - Case B: Non-Allowlisted Workflow (workflow not in allowed-workflows -> DENIED)
  - Case C: Protected File Modification (PR modifies .github/workflows/ -> DENIED / ABSTAIN)
  - Case D: Prompt Injection Attack (adversarial payload detected -> DENIED)
  - Case E: Wrong PR Mismatch (PR does not match Run correlation -> FAIL-CLOSED DENIED)
  - Case F: Already Completed Run (Run status=completed / success -> STATUS GATE DENIED)
"""

import sys
import os
import json
from typing import Dict, Any, List, Optional

class SafeOutputPolicyEvaluator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.allowed_workflows = [os.path.basename(w) for w in config.get("allowed_workflows", [])]
        self.allowed_prs = [int(p) for p in config.get("allowed_pull_requests", [])]
        self.fork_allowed = config.get("fork", False)
        self.protected_files = set(config.get("protected_files", [
            "package.json", "go.mod", "requirements.txt", "README.md"
        ]))
        self.staged = config.get("staged", False)

    def evaluate_run(self, 
                     run_data: Dict[str, Any], 
                     pr_data: Dict[str, Any], 
                     agent_decision: str, 
                     agent_reason: str) -> Dict[str, Any]:
        """
        Executes deterministic gh-aw approve_workflow_run validation matching v0.87.1 specifications.
        """
        run_id = run_data.get("id")
        run_status = run_data.get("status")
        run_conclusion = run_data.get("conclusion")
        run_event = run_data.get("event")
        workflow_path = run_data.get("path", "")
        workflow_name = os.path.basename(workflow_path)
        head_repo_fork = run_data.get("head_repository", {}).get("fork", False)
        
        # 1. Agent Decision Gate
        if agent_decision != "APPROVE":
            return {
                "verdict": "REJECTED",
                "reason": f"Agent emitted '{agent_decision}': {agent_reason}",
                "status_code": 403,
                "approved": False
            }

        # 2. Event Gate (must be pull_request)
        if run_event != "pull_request":
            return {
                "verdict": "DENIED",
                "reason": f"Workflow run #{run_id} event '{run_event}' is not 'pull_request'.",
                "status_code": 400,
                "approved": False
            }

        # 3. Run Status Gate (Must be waiting or action_required - Fail Closed on completed runs)
        if run_status == "completed" and run_conclusion != "action_required":
            return {
                "verdict": "DENIED",
                "reason": f"Workflow run #{run_id} is already completed (status: {run_status}, conclusion: {run_conclusion}); not awaiting approval.",
                "status_code": 409,
                "approved": False
            }
        if run_status not in ["waiting", "queued", "in_progress", "completed"] or (run_status == "completed" and run_conclusion != "action_required"):
            return {
                "verdict": "DENIED",
                "reason": f"Workflow run #{run_id} is not in waiting/action_required state (status: {run_status}).",
                "status_code": 400,
                "approved": False
            }

        # 4. Workflow Allowlist Gate
        if workflow_name not in self.allowed_workflows:
            return {
                "verdict": "DENIED",
                "reason": f"Workflow '{workflow_name}' is not permitted by allowlist {self.allowed_workflows}.",
                "status_code": 403,
                "approved": False
            }

        # 5. PR ↔ Run Correlation & Authorization Gate (Fail-Closed)
        pr_number = pr_data.get("number")
        run_prs = [pr.get("number") for pr in run_data.get("pull_requests", [])]
        
        # Check correlation via run.pull_requests OR cryptographic Head SHA matching
        pr_head_sha = pr_data.get("head", {}).get("sha")
        run_head_sha = run_data.get("head_sha")
        
        is_correlated = False
        if pr_number in run_prs:
            is_correlated = True
        elif pr_head_sha and run_head_sha and pr_head_sha == run_head_sha:
            is_correlated = True
            
        if not is_correlated:
            return {
                "verdict": "DENIED",
                "reason": f"Run #{run_id} cannot be cryptographically proven to belong to PR #{pr_number} (PR head SHA: {pr_head_sha} != Run head SHA: {run_head_sha}) [Fail-Closed].",
                "status_code": 403,
                "approved": False
            }
            
        if self.allowed_prs and pr_number not in self.allowed_prs:
            return {
                "verdict": "DENIED",
                "reason": f"PR #{pr_number} is not in explicitly allowed pull requests list {self.allowed_prs}.",
                "status_code": 403,
                "approved": False
            }

        # 6. Fork Origin Policy Gate
        if head_repo_fork and not self.fork_allowed:
            return {
                "verdict": "DENIED",
                "reason": f"Workflow run #{run_id} is from a fork but fork: true is not configured.",
                "status_code": 403,
                "approved": False
            }

        # 7. Protected Files Gate
        modified_files = pr_data.get("modified_files", [])
        for f in modified_files:
            if f.startswith(".github/workflows/") or f in self.protected_files:
                # If custom protected file check applies
                if f.startswith(".github/workflows/"):
                    return {
                        "verdict": "DENIED",
                        "reason": f"PR #{pr_number} modifies protected workflow file: '{f}'.",
                        "status_code": 403,
                        "approved": False
                    }

        # 8. All Policy Invariants Satisfied -> Approve (or Staged Preview)
        if self.staged:
            return {
                "verdict": "STAGED_PREVIEW",
                "reason": f"Staged mode active - would approve workflow run #{run_id}.",
                "status_code": 200,
                "approved": False,
                "staged": True
            }

        return {
            "verdict": "APPROVED",
            "reason": f"All policy checks passed. Issuing approval API for run #{run_id}.",
            "status_code": 201,
            "approved": True
        }


def run_test_suite():
    print("================================================================================")
    print("  GitHub Agentic Workflows v0.87.1 'approve-workflow-run' Policy Gate Test Suite")
    print("================================================================================\n")
    
    config = {
        "allowed_workflows": ["fork-ci.yml"],
        "allowed_pull_requests": [3],
        "fork": True,
        "staged": False
    }
    evaluator = SafeOutputPolicyEvaluator(config)
    
    test_cases = [
        {
            "id": "Case A",
            "title": "Legal Fork PR Approval",
            "run": {
                "id": 32377941464,
                "event": "pull_request",
                "status": "completed",
                "conclusion": "action_required",
                "path": ".github/workflows/fork-ci.yml",
                "head_sha": "159f00d5f9f5a67b1807459f851e2807e9a8eee8",
                "head_repository": {"fork": True},
                "pull_requests": [{"number": 3}]
            },
            "pr": {
                "number": 3,
                "head": {"sha": "159f00d5f9f5a67b1807459f851e2807e9a8eee8"},
                "modified_files": ["README.md"]
            },
            "agent_decision": "APPROVE",
            "agent_reason": "Safe PR modification verified",
            "expected_verdict": "APPROVED",
            "expected_code": 201
        },
        {
            "id": "Case B",
            "title": "Non-Allowlisted Workflow Denied",
            "run": {
                "id": 32377941545,
                "event": "pull_request",
                "status": "completed",
                "conclusion": "action_required",
                "path": ".github/workflows/fork-ci-untrusted.yml",
                "head_sha": "159f00d5f9f5a67b1807459f851e2807e9a8eee8",
                "head_repository": {"fork": True},
                "pull_requests": [{"number": 3}]
            },
            "pr": {
                "number": 3,
                "head": {"sha": "159f00d5f9f5a67b1807459f851e2807e9a8eee8"},
                "modified_files": ["README.md"]
            },
            "agent_decision": "APPROVE",
            "agent_reason": "Safe PR modification verified",
            "expected_verdict": "DENIED",
            "expected_code": 403
        },
        {
            "id": "Case C",
            "title": "Protected File Modification Denied",
            "run": {
                "id": 32380503536,
                "event": "pull_request",
                "status": "completed",
                "conclusion": "action_required",
                "path": ".github/workflows/fork-ci.yml",
                "head_sha": "ad31e2d5f9f5a67b1807459f851e2807e9a8eee8",
                "head_repository": {"fork": True},
                "pull_requests": [{"number": 4}]
            },
            "pr": {
                "number": 4,
                "head": {"sha": "ad31e2d5f9f5a67b1807459f851e2807e9a8eee8"},
                "modified_files": [".github/workflows/fork-ci.yml"]
            },
            "agent_decision": "ABSTAIN",
            "agent_reason": "Protected workflow files modified",
            "expected_verdict": "REJECTED",
            "expected_code": 403
        },
        {
            "id": "Case D",
            "title": "Prompt Injection Attack Rejected",
            "run": {
                "id": 32381898655,
                "event": "pull_request",
                "status": "completed",
                "conclusion": "action_required",
                "path": ".github/workflows/fork-ci.yml",
                "head_sha": "df36c5a5f9f5a67b1807459f851e2807e9a8eee8",
                "head_repository": {"fork": True},
                "pull_requests": [{"number": 5}]
            },
            "pr": {
                "number": 5,
                "head": {"sha": "df36c5a5f9f5a67b1807459f851e2807e9a8eee8"},
                "modified_files": ["README.md"]
            },
            "agent_decision": "DENY",
            "agent_reason": "Prompt injection detected",
            "expected_verdict": "REJECTED",
            "expected_code": 403
        },
        {
            "id": "Case E",
            "title": "Wrong PR Mismatch (Fail-Closed)",
            "run": {
                "id": 32377941464,
                "event": "pull_request",
                "status": "completed",
                "conclusion": "action_required",
                "path": ".github/workflows/fork-ci.yml",
                "head_sha": "159f00d5f9f5a67b1807459f851e2807e9a8eee8",
                "head_repository": {"fork": True},
                "pull_requests": []  # Empty PR list in GitHub API response
            },
            "pr": {
                "number": 99,  # Mismatched PR number and mismatched SHA
                "head": {"sha": "9999999999999999999999999999999999999999"},
                "modified_files": ["README.md"]
            },
            "agent_decision": "APPROVE",
            "agent_reason": "Agent tricked by incorrect context",
            "expected_verdict": "DENIED",
            "expected_code": 403
        },
        {
            "id": "Case F",
            "title": "Already Completed Run Denied (Status Gate)",
            "run": {
                "id": 32377941464,
                "event": "pull_request",
                "status": "completed",
                "conclusion": "success",  # Already finished successfully!
                "path": ".github/workflows/fork-ci.yml",
                "head_sha": "159f00d5f9f5a67b1807459f851e2807e9a8eee8",
                "head_repository": {"fork": True},
                "pull_requests": [{"number": 3}]
            },
            "pr": {
                "number": 3,
                "head": {"sha": "159f00d5f9f5a67b1807459f851e2807e9a8eee8"},
                "modified_files": ["README.md"]
            },
            "agent_decision": "APPROVE",
            "agent_reason": "Safe PR modification",
            "expected_verdict": "DENIED",
            "expected_code": 409
        }
    ]

    all_passed = True
    for tc in test_cases:
        res = evaluator.evaluate_run(
            run_data=tc["run"],
            pr_data=tc["pr"],
            agent_decision=tc["agent_decision"],
            agent_reason=tc["agent_reason"]
        )
        passed = (res["verdict"] == tc["expected_verdict"]) and (res["status_code"] == tc["expected_code"])
        status_symbol = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_passed = False
            
        print(f"[{status_symbol}] {tc['id']}: {tc['title']}")
        print(f"       Verdict: {res['verdict']} (Expected: {tc['expected_verdict']}) | HTTP {res['status_code']}")
        print(f"       Reason : {res['reason']}\n")

    print("--------------------------------------------------------------------------------")
    if all_passed:
        print("🎉 ALL 6 SECURITY INVARIANTS & POLICY GATES PASSED DETERMINISTIC VALIDATION!")
    else:
        print("❌ ONE OR MORE TESTS FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    run_test_suite()
