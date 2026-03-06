export const environment = {
  production: false,
  apiUrl: "https://teams-ui.kube-playground.io/api", // Use proxy path instead of direct URL
  keycloak: {
    url: "https://kc.kube-playground.io",
    realm: "teams",
    clientId: "teams-ui",
  },
};
