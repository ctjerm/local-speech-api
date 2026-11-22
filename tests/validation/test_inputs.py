import pytest
from test_api import FakeSpeech, FakeTranscriber, audio_file, client


@pytest.mark.parametrize("data,field", [({}, "text"), ({"text": "\t\n "}, "text")])
def test_speech_errors_identify_the_field_before_calling_provider(data, field):
    provider = FakeSpeech()
    with client(speech=provider) as api:
        response = api.post("/v1/audio/speech", data=data)
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", field]
    assert provider.requests == []


@pytest.mark.parametrize("field", ["text", "instruction", "provider_setting"])
def test_file_in_text_field_is_rejected_and_recovery_works(field):
    provider = FakeSpeech()
    with client(speech=provider) as api:
        response = api.post(
            "/v1/audio/speech",
            data={} if field == "text" else {"text": "Hello"},
            files={field: ("unexpected.txt", b"text")},
        )
        assert response.status_code == 422
        assert not provider.requests
        assert api.post("/v1/audio/speech", data={"text": "Hello"}).status_code == 200


def test_provider_specific_text_fields_remain_opaque_to_common_schema():
    provider = FakeSpeech()
    with client(speech=provider) as api:
        response = api.post(
            "/v1/audio/speech",
            data={"text": " Hello ", "instruction": " calm ", "dialect": "regional"},
        )
        assert response.status_code == 200
    request = provider.requests[0]
    assert (request.text, request.instruction) == ("Hello", "calm")
    assert request.provider_options == {"dialect": "regional"}


def test_transcription_requires_an_upload_and_rejects_unknown_options():
    class Counting(FakeTranscriber):
        calls = 0

        def transcribe(self, samples):
            self.calls += 1
            return super().transcribe(samples)

    provider = Counting()
    with client(provider) as api:
        wrong_type = api.post("/v1/audio/transcriptions", data={"file": "server-path.wav"})
        assert wrong_type.status_code == 422
        assert wrong_type.json()["detail"][0]["loc"] == ["body", "file"]
        unknown = api.post(
            "/v1/audio/transcriptions", files=audio_file(), data={"typo": "unused"}
        )
        assert unknown.status_code == 422
        assert unknown.json()["detail"][0]["loc"] == ["body", "typo"]
        assert provider.calls == 0
        assert api.post("/v1/audio/transcriptions", files=audio_file()).status_code == 200
        assert provider.calls == 1


def test_openapi_documents_the_validated_forms_and_capabilities():
    with client() as api:
        schema = api.get("/openapi.json").json()
        models = schema["components"]["schemas"]
        speech = models["SpeechInput"]
        assert speech["properties"]["text"]["minLength"] == 1
        assert speech["required"] == ["text"]
        assert speech["additionalProperties"] == {"type": "string"}
        transcription = models["TranscriptionInput"]
        assert transcription["required"] == ["file"]
        assert (
            transcription["properties"]["file"]["contentMediaType"] == "application/octet-stream"
        )
        assert transcription["additionalProperties"] is False
        for path, name in (
            ("speech", "SpeechCapabilitiesResponse"),
            ("transcriptions", "TranscriptionCapabilitiesResponse"),
        ):
            response = schema["paths"][f"/v1/audio/{path}/capabilities"]["get"]["responses"]["200"]
            assert response["content"]["application/json"]["schema"]["$ref"].endswith(name)
