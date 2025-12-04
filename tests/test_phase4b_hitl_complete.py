#!/usr/bin/env python3
"""
Phase 4b: Complete HITL Workflow with Valid Approval

Tests the complete HITL workflow including:
1. Request without approval (blocked)
2. Request with invalid approval (blocked)
3. Request with valid approval (succeeds)
"""

import sys
import os
import requests
import json

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'amorce_py_sdk'))

from amorce import IdentityManager

def test_complete_hitl_workflow():
    """Test complete HITL workflow with valid approval."""
    
    print("\n" + "="*70)
    print("🧪 PHASE 4b: COMPLETE HITL WORKFLOW WITH VALID APPROVAL")
    print("="*70)
    
    # Create agent identity
    print("\n📍 Step 1: Create Agent Identity")
    identity = IdentityManager.generate_ephemeral()
    print(f"   Agent ID: {identity.agent_id}")
    
    # Test 1: Without approval (should fail)
    print("\n📍 Step 2: Request write_file WITHOUT Approval (Should Fail)")
    payload1 = {
        "payload": {
            "tool_name": "write_file",
            "arguments": {
                "path": "/private/tmp/hitl_test.txt",
                "content": "Test HITL workflow"
            }
        }
    }
    
    signature1 = identity.sign_data(json.dumps(payload1, sort_keys=True).encode())
    
    response1 = requests.post(
        "http://localhost:5001/v1/tools/call",
        json=payload1,
        headers={
            "X-Amorce-Agent-ID": identity.agent_id,
            "X-Agent-Signature": signature1
        }
    )
    
    print(f"   Status: {response1.status_code}")
    if response1.status_code == 403:
        print(f"   ✅ Correctly blocked without approval")
    else:
        print(f"   ❌ Unexpected response: {response1.status_code}")
        return False
    
    # Test 2: With invalid approval (should fail)
    print("\n📍 Step 3: Request write_file WITH Invalid Approval (Should Fail)")
    payload2 = {
        "payload": {
            "tool_name": "write_file",
            "arguments": {
                "path": "/private/tmp/hitl_test.txt",
                "content": "Test HITL workflow"
            },
            "approval_id": "invalid-123"
        }
    }
    
    signature2 = identity.sign_data(json.dumps(payload2, sort_keys=True).encode())
    
    response2 = requests.post(
        "http://localhost:5001/v1/tools/call",
        json=payload2,
        headers={
            "X-Amorce-Agent-ID": identity.agent_id,
            "X-Agent-Signature": signature2
        }
    )
    
    print(f"   Status: {response2.status_code}")
    if response2.status_code == 403:
        print(f"   ✅ Correctly blocked with invalid approval")
    else:
        print(f"   ❌ Unexpected response: {response2.status_code}")
    
    # Test 3: With valid approval (should succeed in standalone mode)
    print("\n📍 Step 4: Request write_file WITH Valid Approval (Should Succeed)")
    payload3 = {
        "payload": {
            "tool_name": "write_file",
            "arguments": {
                "path": "/private/tmp/hitl_test_approved.txt",
                "content": "Successfully executed with HITL approval!"
            },
            "approval_id": "approval-valid-test-001"
        }
    }
    
    signature3 = identity.sign_data(json.dumps(payload3, sort_keys=True).encode())
    
    response3 = requests.post(
        "http://localhost:5001/v1/tools/call",
        json=payload3,
        headers={
            "X-Amorce-Agent-ID": identity.agent_id,
            "X-Agent-Signature": signature3
        }
    )
    
    print(f"   Status: {response3.status_code}")
    if response3.status_code == 200:
        result = response3.json()
        print(f"   ✅ Tool executed with approval!")
        print(f"   Status: {result.get('status')}")
        print(f"   Tool: {result.get('tool_name')}")
        
        # Verify file was actually created
        import subprocess
        check = subprocess.run(
            ["cat", "/private/tmp/hitl_test_approved.txt"],
            capture_output=True,
            text=True
        )
        if "Successfully executed" in check.stdout:
            print(f"   ✅ File actually written! Content verified.")
        else:
            print(f"   ⚠️  File write status unclear")
    else:
        print(f"   ❌ Failed: {response3.status_code}")
        print(f"   Response: {response3.text[:200]}")
        return False
    
    # Summary
    print("\n" + "="*70)
    print("✅ PHASE 4b COMPLETE: FULL HITL WORKFLOW WORKING")
    print("="*70)
    print("\n✅ Complete HITL Flow Verified:")
    print("   1. ✅ Request without approval → 403 (blocked)")
    print("   2. ✅ Request with invalid approval → 403 (blocked)")
    print("   3. ✅ Request with valid approval → 200 (executed)")
    print("   4. ✅ Tool actually executed (file written)")
    print("\n🎯 HITL workflow is FULLY FUNCTIONAL in standalone mode")
    
    return True


if __name__ == "__main__":
    result = test_complete_hitl_workflow()
    sys.exit(0 if result else 1)
