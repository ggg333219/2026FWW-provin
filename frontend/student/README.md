# classroom-system

## Project setup
```
npm install
```

### Compiles and hot-reloads for development
```
npm run serve
```

### Compiles and minifies for production
```
npm run build
```

### Lints and fixes files
```
npm run lint
```

### Customize configuration
See [Configuration Reference](https://cli.vuejs.org/config/).

### Environment
Create `.env.local` from `.env.example` to configure backend API address:

```
copy .env.example .env.local
```

`VUE_APP_API_BASE` defaults to `http://localhost:18080`.

### Project Structure
- `src/config/api.js`: backend base URL config.
- `src/services/studentApi.js`: student-side API request layer.
- `src/styles/theme.css`: global theme tokens and base styles.
