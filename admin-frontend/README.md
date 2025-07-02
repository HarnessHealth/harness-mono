# Harness Admin Frontend

Admin dashboard for the Harness veterinary AI platform.

## Features

- **Model Management**: View, deploy, and rollback AI models
- **Paper Acquisition**: Monitor paper crawling and processing status
- **Evaluation Suite**: Run benchmarks and view results
- **System Health**: Monitor infrastructure and service health

## Development

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

## Environment Variables

Create a `.env` file:

```env
VITE_API_URL=http://localhost:8000
```

## Authentication

Default admin credentials for development:
- Email: admin@harness.health
- Password: admin

## Pages

1. **Dashboard**: Overview of system status
2. **Models**: Manage AI model deployments
3. **Papers**: Monitor paper acquisition pipeline
4. **Evaluation**: Run model evaluations
5. **System**: View system health and metrics