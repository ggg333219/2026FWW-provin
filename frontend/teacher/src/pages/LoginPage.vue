<template>
  <HomeLogin :session-expired="route.query.reason === 'session_expired'" @login-success="handleLoginSuccess" />
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import HomeLogin from '../components/HomeLogin.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const handleLoginSuccess = (user) => {
  authStore.login(user)
  const redirect = router.currentRoute.value.query.redirect || '/courseware/create/s1-intent'
  router.push(redirect)
}
</script>
