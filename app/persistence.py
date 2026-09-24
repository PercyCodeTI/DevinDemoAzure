"""Gravação assíncrona das simulações com fila de reprocessamento (A3, RNF-01)."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable

from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

MAX_TENTATIVAS = 5
INTERVALO_RETRY_S = 5.0


class GravadorAssincrono:
    """Enfileira registros e os grava em thread de fundo, sem bloquear a resposta HTTP."""

    def __init__(
        self,
        engine: Engine,
        inserir: Callable[[Engine, dict], None],
        tamanho_fila: int = 10000,
        intervalo_retry_s: float = INTERVALO_RETRY_S,
    ) -> None:
        self._engine = engine
        self._inserir = inserir
        self._fila: queue.Queue[tuple[dict, int] | None] = queue.Queue(maxsize=tamanho_fila)
        self._intervalo_retry_s = intervalo_retry_s
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()
        self.gravadas = 0
        self.falhas = 0

    def iniciar(self) -> None:
        if self._thread is not None:
            return
        self._parar.clear()
        self._thread = threading.Thread(
            target=self._loop, name="gravador-simulacoes", daemon=True
        )
        self._thread.start()

    def parar(self, timeout: float = 10.0) -> None:
        if self._thread is None:
            return
        self._parar.set()
        self._fila.put(None)
        self._thread.join(timeout=timeout)
        self._thread = None

    def enfileirar(self, registro: dict) -> bool:
        try:
            self._fila.put_nowait((registro, 0))
            return True
        except queue.Full:
            self.falhas += 1
            logger.error("fila_gravacao_cheia", extra={"simulacao_id": registro.get("id")})
            return False

    def drenar(self, timeout: float = 10.0) -> None:
        """Aguarda a fila esvaziar (usado em testes e no shutdown)."""
        limite = time.monotonic() + timeout
        while not self._fila.empty() and time.monotonic() < limite:
            time.sleep(0.01)

    @property
    def pendentes(self) -> int:
        return self._fila.qsize()

    def _loop(self) -> None:
        while not self._parar.is_set() or not self._fila.empty():
            try:
                item = self._fila.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                break
            registro, tentativas = item
            try:
                self._inserir(self._engine, registro)
                self.gravadas += 1
            except Exception:  # noqa: BLE001 - falha não pode derrubar a thread
                tentativas += 1
                logger.exception(
                    "falha_gravacao_simulacao",
                    extra={"simulacao_id": registro.get("id"), "tentativa": tentativas},
                )
                if tentativas >= MAX_TENTATIVAS:
                    self.falhas += 1
                    continue
                threading.Timer(
                    self._intervalo_retry_s * tentativas,
                    self._reenfileirar,
                    args=(registro, tentativas),
                ).start()

    def _reenfileirar(self, registro: dict, tentativas: int) -> None:
        try:
            self._fila.put_nowait((registro, tentativas))
        except queue.Full:
            self.falhas += 1
            logger.error("fila_retry_cheia", extra={"simulacao_id": registro.get("id")})
