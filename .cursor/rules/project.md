# Closy project rules

## Stack
- TypeScript
- React Native
- Expo
- Expo Router

## Goals
- mobile-first cross-platform app
- clean architecture
- scalable code
- reusable components
- strong typing

## Coding rules
- use TypeScript everywhere
- prefer functional components
- prefer small files over giant files
- keep UI components reusable
- avoid unnecessary abstraction
- explain changes clearly
- do not introduce native code unless explicitly requested
- preserve a clean feature-based structure

## Commands
- `npx expo start`
- `npm run lint`
- `npx tsc --noEmit`

## Architecture
- keep routes in `app/`
- keep business logic in `src/features/`
- keep shared utilities in `src/lib/`
- keep shared UI in `src/components/ui/`