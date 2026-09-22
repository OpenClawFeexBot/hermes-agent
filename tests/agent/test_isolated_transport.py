"""Adversarial chunk transfers: no partial dispatch or leaked spools."""
import base64
import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from agent.isolated_channel import Channel
from agent.isolated_protocol import MAX_FRAME, send
from agent import isolated_transport as transport


@pytest.mark.parametrize('fault', ['stale', 'sequence', 'identity', 'direction', 'total',
    'oversize', 'short', 'base64', 'version', 'missing', 'timeout', 'disconnect', 'cancel'])
def test_bad_partial_transfer_closes_spool_without_dispatch(monkeypatch, fault):
    files = []
    original = transport.tempfile.TemporaryFile
    def tracked(*args, **kwargs):
        file = original(*args, **kwargs)
        files.append(file)
        return file
    monkeypatch.setattr(transport.tempfile, 'TemporaryFile', tracked)
    monkeypatch.setattr(transport, 'TRANSFER_TIMEOUT', 0.2)
    a, b = socket.socketpair()
    calls = []
    channel = Channel(a, 'nonce', lambda *args: calls.append(args))
    first = {'v': 1, 'generation': 'nonce', 'chunk': 'a'*32, 'reply_chunk': False,
             'sequence': 0, 'size': MAX_FRAME + 123,
             'data': base64.b64encode(b'x' * transport.CHUNK_BYTES).decode()}
    second = dict(first, sequence=1)
    changes = {'stale': {'generation': 'old'}, 'sequence': {'sequence': 0},
        'identity': {'chunk': 'b'*32}, 'direction': {'reply_chunk': True},
        'total': {'size': transport.MAX_MESSAGE + 1},
        'oversize': {'data': base64.b64encode(b'x'*(transport.CHUNK_BYTES + 1)).decode()},
        'short': {'data': ''}, 'base64': {'data': '?!'}, 'version': {'v': 2}}
    try:
        send(b, first)
        if fault in changes:
            send(b, dict(second, **changes[fault]))
        elif fault == 'missing':
            second.pop('data')
            send(b, second)
        elif fault == 'disconnect':
            b.close()
        elif fault == 'cancel':
            channel.close()
        assert channel.closed.wait(3)
        channel._thread.join(3)
        assert not channel._thread.is_alive()
        assert not calls
        assert all(file.closed for file in files)
        if fault != 'cancel':
            assert files, 'partial transfer did not exercise spooling'
    finally:
        channel.close()
        b.close()


def test_blocked_large_send_is_cancellable_and_releases_spool(monkeypatch):
    files = []
    original = transport.tempfile.TemporaryFile
    def tracked(*args, **kwargs):
        f = original(*args, **kwargs)
        files.append(f)
        return f
    monkeypatch.setattr(transport.tempfile, 'TemporaryFile', tracked)
    a, b = socket.socketpair()
    a.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
    client = Channel(a, 'nonce', lambda *_: None)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(client.call, 'run', 'x' * (MAX_FRAME * 2), None)
        try:
            # Receiving a byte proves the send passed serialization and is live.
            b.settimeout(3)
            assert b.recv(1)
            client.close()
            with pytest.raises((RuntimeError, OSError, EOFError)):
                future.result(timeout=3)
            assert files and all(file.closed for file in files)
            assert not client._pending
        finally:
            client.close()
            b.close()


def test_handshake_receive_honors_socket_timeout():
    from agent.isolated_protocol import receive
    a, b = socket.socketpair()
    a.settimeout(0.1)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(receive, a)
        try:
            # Future timeout is deliberately longer than the socket deadline.
            with pytest.raises(TimeoutError):
                future.result(timeout=2)
            assert future.done(), 'receive ignored the bootstrap socket timeout'
        finally:
            a.shutdown(socket.SHUT_RDWR)
            a.close()
            b.close()


def test_construction_accepts_large_json_context_but_rejects_total_overflow():
    from agent.isolated_protocol import AgentConstruction
    context = [{'role': 'user', 'content': 'x' * (MAX_FRAME + 1)}]
    assert AgentConstruction('delegation', {'prefill_messages': context}).kwargs['prefill_messages'] == context
    with pytest.raises(ValueError, match='limit'):
        AgentConstruction('delegation', {'prefill_messages': ['x' * (transport.MAX_MESSAGE + 1)]})


def test_reassembled_reply_must_match_authenticated_correlation():
    a, b = socket.socketpair()
    called = []
    channel = Channel(a, 'nonce', lambda *args: called.append(args))
    message = json.dumps({'v': 1, 'generation': 'nonce', 'id': 'b'*32,
        'op': 'run', 'payload': 'x' * MAX_FRAME}).encode()
    try:
        for seq, start in enumerate(range(0, len(message), transport.CHUNK_BYTES)):
            send(b, {'v': 1, 'generation': 'nonce', 'chunk': 'a'*32, 'reply_chunk': False,
                'sequence': seq, 'size': len(message),
                'data': base64.b64encode(message[start:start + transport.CHUNK_BYTES]).decode()})
        assert channel.closed.wait(3)
        assert not called
    finally:
        channel.close()
        b.close()
