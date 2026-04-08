export default defineNuxtRouteMiddleware(async () => {
  const auth = useAuth();

  const authenticated = await auth.initialize();
  if (!authenticated) {
    return navigateTo("/auth/login");
  }
});
