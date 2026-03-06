export const environment = {
  production: false,
  apiUrl: "http://teams-ui.kube-playground.io", // Use proxy path instead of direct URL
  keycloak: {
    url: "http://kc.kube-playground.io",
    realm: "teams",
    clientId: "teams-ui",
  },
};
