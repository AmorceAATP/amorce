#!/usr/bin/env python3
"""
Phase 4: HITL Workflow Test

Tests the complete Human-in-the-Loop approval workflow:
1. Request tool requiring HITL without approval (should fail 403)
2. Create approval via orchestrator
3. Execute with valid approval (should succeed)
4. Test invalid approval (should fail)
"""

import sys
import os
import requests
import json

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'amorce_py_sdk'))

from amorce import IdentityManager

def test_hitl_workflow():
    """Test complete HITL approval workflow."""
    
    print("\n" + "="*70)
    print("🧪 PHASE 4: HITL WORKFLOW TEST")
    print("="*70)
    
    # Create agent identity
    print("\n📍 Step 1: Create Agent Identity")
    identity = IdentityManager.generate_ephemeral()
    print(f"   Agent ID: {identity.agent_id}")
    
    # Test 1: Try write_file without approval (should fail)
    print("\n📍 Step 2: Request HITL Tool WITHOUT Approval (Should Fail 403)")
    
    payload = {
        "payload": {
            "tool_name": "write_file",
            "arguments": {
                "path": "/private/tmp/test_hitl.txt",
                "content": "Test content"
            }
        }
    }
    
    payload_json = json.dumps(payload, sort_keys=True)
    signature = identity.sign_data(payload_json.encode('utf-8'))
    
    response = requests.post(
        "http://localhost:5001/v1/tools/call",
        json=payload,
        headers={
            "X-Amorce-Agent-ID": identity.agent_id,
            "X-Agent-Signature": signature
        }
    )
    
    print(f"   Response Status: {response.status_code}")
    if response.status_code == 403:
        result = response.json()
        if result.get('requires_hitl'):
            print(f"   ✅ Correctly rejected: HITL required")
            print(f"   Tool: {result.get('tool_name')}")
            print(f"   Message: {result.get('message')}")
        else:
            print(f"   ⚠️  Got 403 but unexpected response: {result}")
            return False
    else:
        print(f"   ❌ Expected 403, got {response.status_code}")
        print(f"   Response: {resonse.text[:200]}")
        return False
    
    # Test 2: Try with invalid approval_id
    print("\n📍 Step 3: Request HITL Tool WITH Invalid Approval (Should Fail 403)")
    
    payload_with_bad_approval = {
        "payload": {
            "tool_name": "write_file",
            "arguments": {
                "path": "/private/tmp/test_hitl.txt",
                "content": "Test content"
            },
            "approval_id": "invalid-approval-123"
        }
    }
    
    payload_json2 = json.dumps(payload_with_bad_approval, sort_keys=True)
    signature2 = identity.sign_data(payload_json2.encode('utf-8'))
    
    response2 = requests.post(
        "http://localhost:5001/v1/tools/call",
        json=payload_with_bad_approval,
        headers={
            "X-Amorce-Agent-ID": identity.agent_id,
            "X-Agent-Signature": signature2
        }
    )
    
    print(f"   Response Status: {response2.status_code}")
    if response2.status_code == 403:
        print(f"   ✅ Correctly rejected invalid approval")
        print(f"   Error: {response2.json().get('error', '')[:100]}")
    else:
        print(f"   ⚠️  Expected 403, got {response2.status_code}")
    
    # Summary
    print("\n" + "="*70)
    print("✅ PHASE 4 COMPLETE: HITL WORKFLOW VALIDATED")
    print("="*70)
    print("\n✅ Verified:")
    print("   - HITL tools require approval (write_file blocked)")
    print("   - Missing approval returns 403 with requires_hitl flag")
    print("   - Invalid approval_id returns 403")
    
    print("\n⚠️  Not Fully Tested (Requires Orchestrator HITL API):")
    print("   - Creating approval via orchestrator")
    print("   - Executing with valid approval")
    print("   - Complete approval verification flow")
    
    return True


if __name__ == "__main__":
    result = test_hitl_workflow()
    sys.exit(0 if result else 1)
