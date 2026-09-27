from delta_contracts.devices import EmptyPayload
from delta_contracts.iot import LightInput
from delta_core.tools.registry import LocalTool


def register_iot_tools(app):
    async def temperature(arguments):
        state = await app.state.iot.get_state()
        return {'temperature':state.temperature, 'unit':'C', 'source':state.source}

    async def brightness(arguments):
        state = await app.state.iot.get_state()
        return {'brightness':state.brightness, 'unit':'percent', 'source':state.source}

    async def motion(arguments):
        state = await app.state.iot.get_state()
        return {'motion':state.motion, 'source':state.source}

    async def light(arguments):
        state = await app.state.iot.set_light(arguments.enabled)
        return {'enabled':state.desk_light, 'source':state.source}

    for name, description, handler in [
        ('iot.get_temperature', 'Get room temperature in Celsius', temperature),
        ('iot.get_brightness', 'Get ambient brightness percentage', brightness),
        ('iot.get_motion', 'Get motion sensor state', motion),
    ]:
        app.state.tools.register(LocalTool(name, description, EmptyPayload, handler, ['iot:read']))
    app.state.tools.register(LocalTool('iot.set_light', 'Set the desk light on/off; one default light, no named device targeting',
                                       LightInput, light, ['iot:write']))
