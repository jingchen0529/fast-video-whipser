export default defineNuxtRouteMiddleware(async () => {
  const auth = useAuth();

  if (auth.isAuthenticated.value) {
    return navigateTo("/dashboard");
  }

  const authenticated = await auth.initialize();
  if (authenticated) {
    return navigateTo("/dashboard");
  }
});
