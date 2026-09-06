# API-Gateway
# API Gateway

A production-style API Gateway built with **FastAPI**, designed to provide a secure, resilient, and observable entry point for backend microservices.

The gateway sits between clients and backend services and handles authentication, routing, rate limiting, caching, load balancing, health monitoring, circuit breaking, security hardening, and request logging.

---

## ✨ Features

### 🔐 Authentication & Security
- JWT-based authentication
- Protected API endpoints
- Automatic failed-login blocking
- Web Application Firewall (WAF)
- Security response headers
- Input/request validation

### 🚦 Traffic Management
- Request routing to backend services
- Rate limiting
- Load balancing across multiple service replicas
- Health-aware service selection

### ⚡ Performance
- Redis-backed caching
- Reduced unnecessary upstream requests
- Configurable cache behavior

### 🛡️ Resilience
- Health checks for backend services
- Circuit breaker pattern
- Automatic failure detection
- Circuit recovery with `HALF_OPEN` state
- Graceful handling of Redis outages
- Continued gateway operation when Redis is unavailable

### 📊 Observability
- Request logging
- Correlation IDs
- Request latency tracking
- HTTP status monitoring
- Persistent request logs using PostgreSQL

---

## 🏗️ Architecture

```text
                    ┌──────────────┐
                    │    Client    │
                    └──────┬───────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │    API Gateway    │
                 │     FastAPI       │
                 └─────────┬─────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
     ┌─────────┐      ┌──────────┐     ┌────────────┐
     │  Auth   │      │  Redis   │     │ PostgreSQL │
     └─────────┘      └──────────┘     └────────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │  Routing /        │
                 │  Load Balancing   │
                 └─────────┬─────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
      ┌──────────────┐          ┌──────────────┐
      │ User Service │          │ Order Service│
      │   Replica 1  │          │              │
      └──────────────┘          └──────────────┘
              │
      ┌──────────────┐
      │ User Service │
      │   Replica 2  │
      └──────────────┘
