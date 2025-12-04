    def _verify_request_with_standalone(self):
        """
        Verify request with standalone mode support.
        
        In standalone mode (no trust directory), performs basic signature validation
        without fetching public keys. NOT FOR PRODUCTION.
        """
        if self.standalone_mode:
            # DEVELOPMENT MODE: Basic validation only
            # Just check that signature headers are present
            signature = None
            agent_id = None
            
            for key, value in request.headers.items():
                if key.lower() == 'x-agent-signature':
                    signature = value
                elif key.lower() == 'x-amorce-agent-id':
                    agent_id = value
            
            if not signature:
                raise AmorceSecurityError("Missing X-Agent-Signature header")
            if not agent_id:
                raise AmorceSecurityError("Missing X-Amorce-Agent-ID header")
            
            # Parse payload
            import json
            payload = json.loads(request.get_data())
            
            # Return mock verified request (DEVELOPMENT ONLY!)
            logger.warning(f"⚠️  STANDALONE MODE: Accepting request from {agent_id} without key verification")
            
            # Create a simple object to return
            class StandaloneVerified:
                def __init__(self, agent_id, payload):
                    self.agent_id = agent_id
                    self.payload = payload
            
            return StandaloneVerified(agent_id, payload)
        else:
            # PRODUCTION MODE: Full verification with trust directory
            return verify_request(
                headers=request.headers,
                body=request.get_data(),
                directory_url=self.trust_directory_url
            )
