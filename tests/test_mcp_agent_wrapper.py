"""
Comprehensive unit tests for MCP Agent Wrapper

Tests cover:
- Signature verification
- HITL approval workflow
- Tool discovery and execution
- Error handling
- Health checks
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from flask import Flask
import sys
import os

# Add SDK to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'amorce_py_sdk'))

# Mock SDK imports for testing
sys.modules['amorce_py_sdk'] = MagicMock()
sys.modules['amorce_py_sdk.amorce'] = MagicMock()
sys.modules['amorce_py_sdk.amorce.verification'] = MagicMock()
sys.modules['amorce_py_sdk.amorce.exceptions'] = MagicMock()

from adapters.mcp.mcp_agent_wrapper import MCPAgentWrapper
from adapters.mcp.mcp_client import MCPTool


class TestMCPAgentWrapper:
    """Test suite for MCP Agent Wrapper."""
    
    @pytest.fixture
    def wrapper(self):
        """Create wrapper instance for testing."""
        return MCPAgentWrapper(
            mcp_command=["echo", "test"],
            server_name="test-server",
            require_hitl_for=["write_file", "delete_file"],
            port=5999,
            orchestrator_url="http://localhost:8080",
            trust_directory_url="http://localhost:9000"
        )
    
    @pytest.fixture
    def client(self, wrapper):
        """Create Flask test client."""
        wrapper.app.config['TESTING'] = True
        return wrapper.app.test_client()
    
    def test_wrapper_initialization(self, wrapper):
        """Test wrapper initializes correctly."""
        assert wrapper.server_name == "test-server"
        assert wrapper.port == 5999
        assert "write_file" in wrapper.require_hitl
        assert "delete_file" in wrapper.require_hitl
        assert wrapper.orchestrator_url == "http://localhost:8080"
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get('/health')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
        assert data['server'] == 'test-server'
        assert data['type'] == 'mcp-wrapper'
    
    @patch('adapters.mcp.mcp_agent_wrapper.verify_request')
    @patch('adapters.mcp.mcp_agent_wrapper.asyncio.new_event_loop')
    def test_tools_list_success(self, mock_loop, mock_verify, client, wrapper):
        """Test successful tool listing."""
        # Mock verification
        mock_verified = Mock()
        mock_verified.agent_id = 'test-agent'
        mock_verified.payload = {'payload': {}}
        mock_verify.return_value = mock_verified
        
        # Mock async execution
        mock_event_loop = Mock()
        mock_loop.return_value = mock_event_loop
        
        # Mock tools
        mock_tools = [
            MCPTool(
                name="read_file",
                description="Read a file",
                input_schema={"type": "object"}
            ),
            MCPTool(
                name="write_file",
                description="Write a file",
                input_schema={"type": "object"}
            )
        ]
        mock_event_loop.run_until_complete.return_value = mock_tools
        
        response = client.post('/v1/tools/list', json={'payload': {}})
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert 'tools' in data
        assert len(data['tools']) == 2
        assert data['tools'][0]['name'] == 'read_file'
        assert data['tools'][1]['requires_approval'] == True  # write_file requires HITL
    
    @patch('adapters.mcp.mcp_agent_wrapper.verify_request')
    def test_tools_list_auth_failure(self, mock_verify, client):
        """Test tools list with invalid signature."""
        from amorce_py_sdk.amorce.exceptions import AmorceSecurityError
        mock_verify.side_effect = AmorceSecurityError("Invalid signature")
        
        response = client.post('/v1/tools/list', json={'payload': {}})
        assert response.status_code == 401
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Unauthorized' in data['error']
    
    @patch('adapters.mcp.mcp_agent_wrapper.verify_request')
    @patch('adapters.mcp.mcp_agent_wrapper.asyncio.new_event_loop')
    def test_tool_call_success(self, mock_loop, mock_verify, client, wrapper):
        """Test successful tool execution (no HITL required)."""
        # Mock verification
        mock_verified = Mock()
        mock_verified.agent_id = 'test-agent'
        mock_verified.payload = {
            'payload': {
                'tool_name': 'read_file',
                'arguments': {'path': '/tmp/test.txt'}
            }
        }
        mock_verify.return_value = mock_verified
        
        # Mock async execution
        mock_event_loop = Mock()
        mock_loop.return_value = mock_event_loop
        mock_event_loop.run_until_complete.return_value = {"content": "test data"}
        
        response = client.post('/v1/tools/call', json={
            'payload': {
                'tool_name': 'read_file',
                'arguments': {'path': '/tmp/test.txt'}
            }
        })
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'success'
        assert data['tool_name'] == 'read_file'
        assert 'result' in data
    
    @patch('adapters.mcp.mcp_agent_wrapper.verify_request')
    def test_tool_call_missing_tool_name(self, mock_verify, client):
        """Test tool call with missing tool name."""
        mock_verified = Mock()
        mock_verified.agent_id = 'test-agent'
        mock_verified.payload = {'payload': {'arguments': {}}}
        mock_verify.return_value = mock_verified
        
        response = client.post('/v1/tools/call', json={'payload': {'arguments': {}}})
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Missing tool_name' in data['error']
    
    @patch('adapters.mcp.mcp_agent_wrapper.verify_request')
    def test_tool_call_hitl_required_no_approval(self, mock_verify, client):
        """Test tool requiring HITL without approval."""
        mock_verified = Mock()
        mock_verified.agent_id = 'test-agent'
        mock_verified.payload = {
            'payload': {
                'tool_name': 'write_file',
                'arguments': {'path': '/tmp/test.txt', 'content': 'data'}
            }
        }
        mock_verify.return_value = mock_verified
        
        response = client.post('/v1/tools/call', json={
            'payload': {
                'tool_name': 'write_file',
                'arguments': {'path': '/tmp/test.txt', 'content': 'data'}
            }
        })
        
        assert response.status_code == 403
        data = json.loads(response.data)
        assert data['requires_hitl'] == True
        assert data['tool_name'] == 'write_file'
    
    @patch('adapters.mcp.mcp_agent_wrapper.verify_request')
    @patch('adapters.mcp.mcp_agent_wrapper.requests.get')
    @patch('adapters.mcp.mcp_agent_wrapper.asyncio.new_event_loop')
    def test_tool_call_hitl_with_valid_approval(self, mock_loop, mock_requests, mock_verify, client):
        """Test tool with valid HITL approval."""
        # Mock verification
        mock_verified = Mock()
        mock_verified.agent_id = 'test-agent'
        mock_verified.payload = {
            'payload': {
                'tool_name': 'write_file',
                'arguments': {'path': '/tmp/test.txt', 'content': 'data'},
                'approval_id': 'approval-123'
            }
        }
        mock_verify.return_value = mock_verified
        
        # Mock approval verification
        mock_approval_response = Mock()
        mock_approval_response.status_code = 200
        mock_approval_response.json.return_value = {
            'status': 'approved',
            'agent_id': 'test-agent'
        }
        mock_requests.return_value = mock_approval_response
        
        # Mock tool execution
        mock_event_loop = Mock()
        mock_loop.return_value = mock_event_loop
        mock_event_loop.run_until_complete.return_value = {"success": True}
        
        response = client.post('/v1/tools/call', json={
            'payload': {
                'tool_name': 'write_file',
                'arguments': {'path': '/tmp/test.txt', 'content': 'data'},
                'approval_id': 'approval-123'
            }
        })
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'success'
    
    @patch('adapters.mcp.mcp_agent_wrapper.verify_request')
    @patch('adapters.mcp.mcp_agent_wrapper.requests.get')
    def test_tool_call_hitl_with_invalid_approval(self, mock_requests, mock_verify, client):
        """Test tool with invalid HITL approval."""
        mock_verified = Mock()
        mock_verified.agent_id = 'test-agent'
        mock_verified.payload = {
            'payload': {
                'tool_name': 'write_file',
                'arguments': {'path': '/tmp/test.txt', 'content': 'data'},
                'approval_id': 'invalid-approval'
            }
        }
        mock_verify.return_value = mock_verified
        
        # Mock invalid approval
        mock_approval_response = Mock()
        mock_approval_response.status_code = 404
        mock_requests.return_value = mock_approval_response
        
        response = client.post('/v1/tools/call', json={
            'payload': {
                'tool_name': 'write_file',
                'arguments': {'path': '/tmp/test.txt', 'content': 'data'},
                'approval_id': 'invalid-approval'
            }
        })
        
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'Invalid or expired approval' in data['error']
    
    def test_verify_approval_success(self, wrapper):
        """Test successful approval verification."""
        with patch('adapters.mcp.mcp_agent_wrapper.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'status': 'approved',
                'agent_id': 'test-agent'
            }
            mock_get.return_value = mock_response
            
            result = wrapper._verify_approval('approval-123', 'write_file', 'test-agent')
            assert result == True
    
    def test_verify_approval_wrong_agent(self, wrapper):
        """Test approval verification with wrong agent."""
        with patch('adapters.mcp.mcp_agent_wrapper.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'status': 'approved',
                'agent_id': 'different-agent'
            }
            mock_get.return_value = mock_response
            
            result = wrapper._verify_approval('approval-123', 'write_file', 'test-agent')
            assert result == False
    
    def test_verify_approval_not_approved(self, wrapper):
        """Test approval verification with pending approval."""
        with patch('adapters.mcp.mcp_agent_wrapper.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'status': 'pending',
                'agent_id': 'test-agent'
            }
            mock_get.return_value = mock_response
            
            result = wrapper._verify_approval('approval-123', 'write_file', 'test-agent')
            assert result == False


class TestMCPAgentWrapperErrorHandling:
    """Test error handling in MCP wrapper."""
    
    @pytest.fixture
    def wrapper(self):
        return MCPAgentWrapper(
            mcp_command=["echo", "test"],
            server_name="test-server",
            port=5999
        )
    
    @pytest.fixture
    def client(self, wrapper):
        wrapper.app.config['TESTING'] = True
        return wrapper.app.test_client()
    
    @patch('adapters.mcp.mcp_agent_wrapper.verify_request')
    @patch('adapters.mcp.mcp_agent_wrapper.asyncio.new_event_loop')
    def test_tool_call_timeout_error(self, mock_loop, mock_verify, client):
        """Test tool call with timeout error."""
        import subprocess
        
        mock_verified = Mock()
        mock_verified.agent_id = 'test-agent'
        mock_verified.payload = {
            'payload': {
                'tool_name': 'slow_tool',
                'arguments': {}
            }
        }
        mock_verify.return_value = mock_verified
        
        mock_event_loop = Mock()
        mock_loop.return_value = mock_event_loop
        mock_event_loop.run_until_complete.side_effect = subprocess.TimeoutExpired("cmd", 30)
        
        response = client.post('/v1/tools/call', json={
            'payload': {'tool_name': 'slow_tool', 'arguments': {}}
        })
        
        assert response.status_code == 504
        data = json.loads(response.data)
        assert 'timeout' in data['error'].lower()
    
    @patch('adapters.mcp.mcp_agent_wrapper.verify_request')
    @patch('adapters.mcp.mcp_agent_wrapper.asyncio.new_event_loop')
    def test_tool_call_connection_error(self, mock_loop, mock_verify, client):
        """Test tool call with connection error."""
        mock_verified = Mock()
        mock_verified.agent_id = 'test-agent'
        mock_verified.payload = {
            'payload': {
                'tool_name': 'broken_tool',
                'arguments': {}
            }
        }
        mock_verify.return_value = mock_verified
        
        mock_event_loop = Mock()
        mock_loop.return_value = mock_event_loop
        mock_event_loop.run_until_complete.side_effect = ConnectionError("Connection failed")
        
        response = client.post('/v1/tools/call', json={
            'payload': {'tool_name': 'broken_tool', 'arguments': {}}
        })
        
        assert response.status_code == 503
        data = json.loads(response.data)
        assert 'unavailable' in data['error'].lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
