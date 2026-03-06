import { KeycloakConfig } from 'keycloak-js';

const keycloakConfig: KeycloakConfig = {
  url: 'http://kc.kube-playground.io',
  realm: 'teams',
  clientId: 'teams-ui',
};

export default keycloakConfig;
