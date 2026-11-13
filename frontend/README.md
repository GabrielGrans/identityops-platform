# IdentityOps Frontend

React and TypeScript frontend for the IdentityOps identity and access management platform.

## Technology Stack

- React
- TypeScript
- Vite
- Lucide React

## Implemented Screens

### Login
- User authentication through the FastAPI backend.
- JWT access-token handling.
- Session validation.

### Dashboard
- Main application overview.
- Identity management interface.
- Dashboard indicators and activity presentation.

### Employees
- Employee directory connected to the backend API.
- Employee information display.
- Search and filtering.

## Roadmap

The following navigation modules are planned but are not yet implemented as complete frontend screens:

- Departments
- Access Groups
- Permissions

## Requirements

- Node.js 22 or newer.
- npm.
- IdentityOps FastAPI backend running locally.

## Installation

From the project root:

```powershell
cd frontend
npm install
```

## Configuration

The API client uses the following default address:

```text
http://127.0.0.1:8000
```

To override it, create a `.env.local` file in the frontend directory:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
```

Vite loads environment variables prefixed with `VITE_`.

Do not place secrets or private credentials in frontend environment variables. Values exposed to Vite are included in the client-side application.

## Development

Start the development server:

```powershell
npm run dev
```

Open:

http://localhost:5173

## Validation

Run ESLint:

```powershell
npm run lint
```

Build the production frontend:

```powershell
npm run build
```

Preview the production build:

```powershell
npm run preview
```

## Backend Integration

The API client is located at:

```text
src/services/api.ts
```

It provides the frontend communication layer for:

- Authentication: `POST /auth/login`
- Current employee: `GET /auth/me`
- Employee directory: `GET /employees`

Authenticated requests use the JWT Bearer token.

## Project Structure

```text
src/
├── assets/
├── services/
│   └── api.ts
├── App.tsx
├── EmployeesPage.tsx
├── LoginPage.tsx
├── App.css
├── index.css
└── main.tsx
```

## License

This frontend is part of the IdentityOps Platform project and is distributed under the MIT License.
