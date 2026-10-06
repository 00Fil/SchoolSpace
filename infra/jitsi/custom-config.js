// Tema e comportamento della stanza allineati al gestionale (accodato a config.js).
config.dynamicBrandingUrl = '/static/lumen/branding.json';
config.defaultLanguage = 'it';
config.disableThirdPartyRequests = true;
config.prejoinConfig = { enabled: false };
config.disableDeepLinking = true;
config.disableInviteFunctions = true;
// Il nome viene dal gestionale (studente/tutor): non modificabile in stanza.
config.readOnlyName = true;
config.disableProfile = true;
config.hideAddRoomButton = true;
config.disableReactionsModeration = true;
config.fileRecordingsEnabled = false;
config.liveStreamingEnabled = false;
config.transcription = { enabled: false };
// Solo i comandi utili a una lezione: meno distrazioni per gli studenti.
config.toolbarButtons = [
  'microphone', 'camera', 'desktop', 'raisehand', 'chat',
  'participants-pane', 'tileview', 'fullscreen', 'settings', 'hangup'
];
config.toolbarConfig = { initialTimeout: 20000, timeout: 6000, alwaysVisible: false };
config.notifications = [
  'connection.CONNFAIL', 'dialog.kickTitle', 'dialog.reservationError', 'dialog.sessTerminated',
  'notify.moderator', 'notify.raisedHand', 'notify.mutedRemotelyTitle', 'notify.kickParticipant',
  'toolbar.noAudioSignalTitle', 'toolbar.noisyAudioInputTitle', 'toolbar.talkWhileMutedPopup'
];
