from django.db import models


class WorkerHeartbeat(models.Model):
    """Ultimo segnale di vita per coda Celery (aggiornato ogni 30 s dal task heartbeat).

    Una riga per coda: lo stato è sovrascritto, non è un log. Il valore assente o
    vecchio fa scattare l'alert "heartbeat assente" (GAP-K03) e, se richiesto, la
    readiness. Dato tecnico, senza dati personali.
    """

    queue = models.CharField(max_length=40, primary_key=True)
    hostname = models.CharField(max_length=200, blank=True)
    build = models.CharField(max_length=80, blank=True)
    seen_at = models.DateTimeField()

    class Meta:
        verbose_name = "heartbeat worker"
        verbose_name_plural = "heartbeat worker"

    def __str__(self):
        return f"{self.queue}@{self.hostname}"
