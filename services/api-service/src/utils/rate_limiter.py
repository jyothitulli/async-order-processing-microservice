import time

class RateLimiter:  # <--- Ensure this name matches the import exactly
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests = {}

    def allow_request(self, client_ip: str) -> bool:
        now = time.time()
        # Basic logic for the rate limiter
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        
        # Filter out old requests
        self.requests[client_ip] = [t for t in self.requests[client_ip] if now - t < self.window_seconds]
        
        if len(self.requests[client_ip]) < self.limit:
            self.requests[client_ip].append(now)
            return True
        return False