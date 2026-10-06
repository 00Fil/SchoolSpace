import ipaddress

from . import conf


def _valid(value):
    try:
        return str(ipaddress.ip_address(value.strip()))
    except (ValueError, AttributeError):
        return None


def client_ip(request):
    """IP del client: REMOTE_ADDR, oppure l'ultimo hop aggiunto dai proxy fidati."""
    hops = int(conf.get("TRUSTED_PROXY_HOPS") or 0)
    remote = _valid(request.META.get("REMOTE_ADDR", ""))
    if hops <= 0:
        return remote
    forwarded = [
        x for x in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if x.strip()
    ]
    if len(forwarded) < hops:
        return remote
    return _valid(forwarded[-hops]) or remote


def ip_in_networks(ip, networks):
    if not ip:
        return False
    address = ipaddress.ip_address(ip)
    return any(address in ipaddress.ip_network(net, strict=False) for net in networks)
