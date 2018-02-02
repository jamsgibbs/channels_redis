import asyncio

import async_timeout
import pytest
from async_generator import async_generator, yield_

from asgi_redis.core import RedisChannelLayer

TEST_HOSTS = [("localhost", 6379)]


@pytest.fixture()
@async_generator
async def channel_layer():
    """
    Channel layer fixture that flushes automatically.
    """
    channel_layer = RedisChannelLayer(hosts=TEST_HOSTS)
    await yield_(channel_layer)
    await channel_layer.flush()
    await channel_layer.close()


@pytest.mark.asyncio
async def test_send_receive(channel_layer):
    """
    Makes sure we can send a message to a normal channel then receive it.
    """
    await channel_layer.send(
        "test-channel-1",
        {
            "type": "test.message",
            "text": "Ahoy-hoy!",
        },
    )
    message = await channel_layer.receive("test-channel-1")
    assert message["type"] == "test.message"
    assert message["text"] == "Ahoy-hoy!"


@pytest.mark.asyncio
async def test_process_local_send_receive(channel_layer):
    """
    Makes sure we can send a message to a process-local channel then receive it.
    """
    channel_name = channel_layer.new_channel()
    await channel_layer.send(
        channel_name,
        {
            "type": "test.message",
            "text": "Local only please",
        },
    )
    message = await channel_layer.receive(channel_name)
    assert message["type"] == "test.message"
    assert message["text"] == "Local only please"


@pytest.mark.asyncio
async def test_multi_send_receive(channel_layer):
    """
    Tests overlapping sends and receives, and ordering.
    """
    channel_layer = RedisChannelLayer(hosts=TEST_HOSTS)
    await channel_layer.send("test-channel-3", {"type": "message.1"})
    await channel_layer.send("test-channel-3", {"type": "message.2"})
    await channel_layer.send("test-channel-3", {"type": "message.3"})
    assert (await channel_layer.receive("test-channel-3"))["type"] == "message.1"
    assert (await channel_layer.receive("test-channel-3"))["type"] == "message.2"
    assert (await channel_layer.receive("test-channel-3"))["type"] == "message.3"


@pytest.mark.asyncio
async def test_reject_bad_channel(channel_layer):
    """
    Makes sure sending/receiving on an invalic channel name fails.
    """
    with pytest.raises(TypeError):
        await channel_layer.send("=+135!", {"type": "foom"})
    with pytest.raises(TypeError):
        await channel_layer.receive("=+135!")


@pytest.mark.asyncio
async def test_reject_bad_client_prefix(channel_layer):
    """
    Makes sure receiving on a non-prefixed local channel is not allowed.
    """
    with pytest.raises(AssertionError):
        await channel_layer.receive("not-client-prefix!local_part")


@pytest.mark.asyncio
async def test_groups_basic(channel_layer):
    """
    Tests basic group operation.
    """
    channel_layer = RedisChannelLayer(hosts=TEST_HOSTS)
    await channel_layer.group_add("test-group", "test-gr-chan-1")
    await channel_layer.group_add("test-group", "test-gr-chan-2")
    await channel_layer.group_add("test-group", "test-gr-chan-3")
    await channel_layer.group_discard("test-group", "test-gr-chan-2")
    await channel_layer.group_send("test-group", {"type": "message.1"})
    # Make sure we get the message on the two channels that were in
    async with async_timeout.timeout(1):
        assert (await channel_layer.receive("test-gr-chan-1"))["type"] == "message.1"
        assert (await channel_layer.receive("test-gr-chan-3"))["type"] == "message.1"
    # Make sure the removed channel did not get the message
    with pytest.raises(asyncio.TimeoutError):
        async with async_timeout.timeout(1):
            await channel_layer.receive("test-gr-chan-2")
