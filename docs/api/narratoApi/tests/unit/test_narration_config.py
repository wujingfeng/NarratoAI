from narrato_api.config import Settings
from narrato_api.integrations.core_client import CoreVoiceCapability
from narrato_api.products.narration_config import get_short_drama_narration_config


class FakeCoreClient:
    def get_voice_capabilities(self):
        return (
            CoreVoiceCapability(
                voice_id="voice_volcengine_cancan",
                name="灿灿 2.0",
                provider_code="volcengine",
                languages=("zh-CN",),
                gender="female",
                styles=("narration",),
                sample_url="https://cdn.example.test/cancan.wav",
            ),
            CoreVoiceCapability(
                voice_id="voice_volcengine_qingcang",
                name="擎苍 2.0",
                provider_code="volcengine",
                languages=("zh-CN",),
                gender="male",
                styles=("narration",),
                sample_url=None,
            ),
        )


def test_short_drama_config_exposes_only_core_catalog_voices(monkeypatch) -> None:
    """设置页所需选项只能由业务 API 配置提供。"""

    monkeypatch.setattr(
        "narrato_api.products.narration_config.HttpCoreClient",
        lambda **_kwargs: FakeCoreClient(),
    )
    config = get_short_drama_narration_config(
        "req_test", Settings(core_request_token="configured")
    ).data
    assert config is not None
    assert [item.name for item in config.narration_styles] == [
        "霸总/甜宠",
        "逆袭/复仇",
        "家庭伦理",
        "古装/权谋",
        "悬疑/犯罪",
        "都市情感",
        "年代/乡村",
        "自定义类型",
    ]
    assert config.narration_styles[0].description == "强情绪拉扯，突出心动与反转"
    assert config.narration_styles[0].tags == ["甜宠", "强代入"]
    assert config.narration_styles[-1].is_custom is True
    assert [item.name for item in config.video_ratios] == [
        "9:16",
        "16:9",
        "4:3",
        "3:4",
        "1:1",
    ]
    assert [(item.id, item.name) for item in config.voices] == [
        ("voice_volcengine_cancan", "灿灿 2.0"),
        ("voice_volcengine_qingcang", "擎苍 2.0"),
    ]
    assert config.voices[0].provider_code == "volcengine"
    assert config.voices[0].languages == ["zh-CN"]
    assert config.voices[0].gender == "female"
    assert config.voices[0].styles == ["narration"]
    assert config.voices[0].sample_url == "https://cdn.example.test/cancan.wav"
    assert [item.name for item in config.subtitle_styles] == [
        "霓虹描边",
        "经典白色",
        "白字蓝边",
    ]
    assert config.original_sound_ratios == list(range(0, 100, 10))
