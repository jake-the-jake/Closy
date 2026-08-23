# Closy

Closy currently has three deliberately separate implementation areas:

- `src/`: the Expo 55 / React Native mobile wardrobe app.
- `engine/`: the standalone C++17 avatar/rendering prototype.
- `closy-forge/`: the Python headless avatar-and-garment package toolchain for deterministic `.closygarment` construction and validation.

The mobile app remains TypeScript-only. Closy Forge is a local/offline service-side R&D/tooling layer and is not imported into the Expo bundle.

See [docs/closy-garment-package-v1.md](docs/closy-garment-package-v1.md) and [closy-forge/README.md](closy-forge/README.md) for the Forge package contract and setup.

## Expo App

This is an [Expo](https://expo.dev) project created with [`create-expo-app`](https://www.npmjs.com/package/create-expo-app).

## Get started

1. Install dependencies

   ```bash
   npm install
   ```

2. Start the app

   ```bash
   npx expo start
   ```

In the output, you'll find options to open the app in a:

- [development build](https://docs.expo.dev/develop/development-builds/introduction/)
- [Android emulator](https://docs.expo.dev/workflow/android-studio-emulator/)
- [iOS simulator](https://docs.expo.dev/workflow/ios-simulator/)
- [Expo Go](https://expo.dev/go), a limited sandbox for trying out app development

You can start developing by editing the files inside the **app** directory. This project uses [file-based routing](https://docs.expo.dev/router/introduction).

## Get a fresh project

When you're ready, run:

```bash
npm run reset-project
```

This command will move the starter code to the **app-example** directory and create a blank **app** directory where you can start developing.

### Other setup steps

- To set up ESLint for linting, run `npx expo lint`, or follow the Expo guide on [Using ESLint and Prettier](https://docs.expo.dev/guides/using-eslint/).
- To set up unit testing, follow the Expo guide on [Unit Testing with Jest](https://docs.expo.dev/develop/unit-testing/).
- Learn more about the TypeScript setup in the Expo guide on [Using TypeScript](https://docs.expo.dev/guides/typescript/).

## Learn more

To learn more about developing with Expo, see:

- [Expo documentation](https://docs.expo.dev/)
- [Learn Expo tutorial](https://docs.expo.dev/tutorial/introduction/)

## Join the community

- [Expo on GitHub](https://github.com/expo/expo)
- [Discord community](https://chat.expo.dev)
