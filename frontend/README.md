# ContribNow Frontend

Vite + React + TypeScript + Tailwind CSS frontend for generating AI-powered onboarding guides.

## Setup

```bash
npm install
```

## Development

```bash
npm run dev        # Start dev server at http://localhost:5173
```

## Build

```bash
npm run build      # Type-check + production build to dist/
npm run preview    # Preview the production build locally
```

## Testing

```bash
npm test                # Run all tests once
npm run test:watch      # Run tests in watch mode
npm run test:coverage   # Run tests with coverage report
```

### Coverage

Tests cover all components, hooks, and the API client. Current coverage:

| Metric     | Coverage |
|------------|----------|
| Statements | 100%     |
| Branches   | 100%     |
| Functions  | 100%     |
| Lines      | 100%     |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API URL |
| `VITE_USE_MOCK` | `false` | Set to `true` to use mock data (access key: `test`) |

Copy `.env.example` to `.env` and adjust as needed.
