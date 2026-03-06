import { KeycloakConfig } from 'keycloak-js';

const keycloakConfig: KeycloakConfig = {
  url: 'https://kc.kube-playground.io',
  realm: 'teams',
  clientId: 'teams-ui',
};

export default keycloakConfig;
