import base64
import json


def calculate_token_info(session_token):
    """
    Calculates the token's payload
    :param session_token:
    :return:
    """
    # JWT = Base64(Header).Base64(Payload).Signature
    try:
        if isinstance(session_token, str):
            session_token = session_token.encode("utf-8")
        payload = session_token.rsplit(b".", 1)[0].split(b".", 1)[1]
        decoded_token_info = base64_decode(payload)
        return json.loads(decoded_token_info)
    except Exception as e:
        # Invalid token returning empty unparsable object
        print("Error getting token info {}".format(e))
        return {}

def base64_decode(input):
    if isinstance(input, str):
        input = input.encode("ascii")
    r = len(input) % 4
    if r > 0:
        input += b"=" * (4 - r)
    return base64.urlsafe_b64decode(input)