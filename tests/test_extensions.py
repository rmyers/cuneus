from cuneus.core.extensions import BaseExtension


async def test_base_extension(mocker):
    b = BaseExtension()
    state = await b.startup(mocker.Mock(), mocker.Mock())
    assert state == {}
