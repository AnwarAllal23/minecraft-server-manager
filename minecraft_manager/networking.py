from __future__ import annotations

from dataclasses import dataclass
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .i18n import tr


MINECRAFT_PROTOCOL = "TCP"


@dataclass
class PortMappingResult:
    ok: bool
    message: str
    public_ip: str = ""
    local_ip: str = ""
    connect_address: str = ""
    router: str = ""


def local_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def public_ip(timeout: float = 4.0) -> str:
    services = (
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
        "https://ifconfig.me/ip",
    )
    for url in services:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                value = response.read(128).decode("utf-8", errors="replace").strip()
            if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", value):
                return value
        except (OSError, urllib.error.URLError, TimeoutError):
            continue
    return ""


def connection_address(port: int, ip: str = "") -> str:
    ip = ip or public_ip()
    if not ip:
        return ""
    return ip if port == 25565 else f"{ip}:{port}"


def open_minecraft_port(port: int, description: str = "Minecraft Server") -> PortMappingResult:
    local_ip = local_lan_ip()
    external_ip = public_ip()
    upnp = _discover_upnp_gateway()
    if not upnp:
        address = connection_address(port, external_ip)
        return PortMappingResult(
            ok=False,
            message=tr(
                "Aucun routeur UPnP detecte. Active UPnP sur le routeur, ou cree une redirection "
                "manuelle TCP {port} vers {ip}:{port}."
            ).format(port=port, ip=local_ip),
            public_ip=external_ip,
            local_ip=local_ip,
            connect_address=address,
        )

    control_url, service_type, router = upnp
    try:
        existing = _soap(
            control_url,
            service_type,
            "GetSpecificPortMappingEntry",
            {
                "NewRemoteHost": "",
                "NewExternalPort": str(port),
                "NewProtocol": MINECRAFT_PROTOCOL,
            },
        )
        existing_client = _xml_value(existing, "NewInternalClient")
        existing_port = _xml_value(existing, "NewInternalPort")
        if existing_client == local_ip and existing_port == str(port):
            address = connection_address(port, external_ip)
            return PortMappingResult(
                ok=True,
                message=tr("Le port etait deja ouvert automatiquement sur ce routeur."),
                public_ip=external_ip,
                local_ip=local_ip,
                connect_address=address,
                router=router,
            )
        if existing_client:
            address = connection_address(port, external_ip)
            return PortMappingResult(
                ok=False,
                message=tr("Le port {port} est deja redirige vers {client}:{internal_port}.").format(port=port, client=existing_client, internal_port=existing_port),
                public_ip=external_ip,
                local_ip=local_ip,
                connect_address=address,
                router=router,
            )
    except RuntimeError:
        pass

    try:
        _soap(
            control_url,
            service_type,
            "AddPortMapping",
            {
                "NewRemoteHost": "",
                "NewExternalPort": str(port),
                "NewProtocol": MINECRAFT_PROTOCOL,
                "NewInternalPort": str(port),
                "NewInternalClient": local_ip,
                "NewEnabled": "1",
                "NewPortMappingDescription": description[:64],
                "NewLeaseDuration": "0",
            },
        )
    except RuntimeError as exc:
        address = connection_address(port, external_ip)
        return PortMappingResult(
            ok=False,
            message=tr(
                "Le routeur a refuse l'ouverture UPnP du port {port}: {error}. "
                "Redirection manuelle a creer: TCP {port} vers {ip}:{port}."
            ).format(port=port, error=exc, ip=local_ip),
            public_ip=external_ip,
            local_ip=local_ip,
            connect_address=address,
            router=router,
        )

    address = connection_address(port, external_ip)
    return PortMappingResult(
        ok=True,
        message=tr("Port TCP {port} ouvert automatiquement vers {ip}:{port}.").format(port=port, ip=local_ip),
        public_ip=external_ip,
        local_ip=local_ip,
        connect_address=address,
        router=router,
    )


@dataclass
class PortMapping:
    external_port: int
    protocol: str
    internal_client: str
    internal_port: int
    description: str
    enabled: bool


def list_port_mappings(candidate_ports: "list[int] | None" = None) -> tuple[list[PortMapping], str]:
    """List UPnP port mappings on the router.

    Some routers (e.g. Freebox) do not implement ``GetGenericPortMappingEntry``
    and report an empty list even when mappings exist, while
    ``GetSpecificPortMappingEntry`` for the same port works fine. So this
    first tries the generic enumeration, then checks each port in
    ``candidate_ports`` individually to catch mappings the enumeration missed.

    Returns ``(mappings, error)``. ``error`` is empty on success.
    """
    upnp = _discover_upnp_gateway()
    if not upnp:
        return [], tr("Aucun routeur UPnP detecte.")

    control_url, service_type, _router = upnp
    mappings: list[PortMapping] = []
    seen_ports: set[int] = set()
    index = 0
    while True:
        try:
            result = _soap(
                control_url,
                service_type,
                "GetGenericPortMappingEntry",
                {"NewPortMappingIndex": str(index)},
            )
        except RuntimeError:
            break
        external_port = _xml_value(result, "NewExternalPort")
        if not external_port:
            break
        mappings.append(
            PortMapping(
                external_port=int(external_port),
                protocol=_xml_value(result, "NewProtocol"),
                internal_client=_xml_value(result, "NewInternalClient"),
                internal_port=int(_xml_value(result, "NewInternalPort") or "0"),
                description=_xml_value(result, "NewPortMappingDescription"),
                enabled=_xml_value(result, "NewEnabled") in ("1", "true", "True"),
            )
        )
        seen_ports.add(int(external_port))
        index += 1
        if index > 200:
            break

    for port in candidate_ports or []:
        if port in seen_ports:
            continue
        for protocol in ("TCP", "UDP"):
            try:
                result = _soap(
                    control_url,
                    service_type,
                    "GetSpecificPortMappingEntry",
                    {"NewRemoteHost": "", "NewExternalPort": str(port), "NewProtocol": protocol},
                )
            except RuntimeError:
                continue
            mappings.append(
                PortMapping(
                    external_port=port,
                    protocol=protocol,
                    internal_client=_xml_value(result, "NewInternalClient"),
                    internal_port=int(_xml_value(result, "NewInternalPort") or "0"),
                    description=_xml_value(result, "NewPortMappingDescription"),
                    enabled=_xml_value(result, "NewEnabled") in ("1", "true", "True"),
                )
            )
            seen_ports.add(port)
    return mappings, ""


def delete_port_mapping(external_port: int, protocol: str = "TCP") -> tuple[bool, str]:
    upnp = _discover_upnp_gateway()
    if not upnp:
        return False, tr("Aucun routeur UPnP detecte.")

    control_url, service_type, _router = upnp
    try:
        _soap(
            control_url,
            service_type,
            "DeletePortMapping",
            {
                "NewRemoteHost": "",
                "NewExternalPort": str(external_port),
                "NewProtocol": protocol,
            },
        )
        return True, ""
    except RuntimeError as exc:
        return False, str(exc)


def _discover_upnp_gateway(timeout: float = 3.0) -> tuple[str, str, str] | None:
    targets = (
        "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
        "urn:schemas-upnp-org:service:WANIPConnection:1",
        "urn:schemas-upnp-org:service:WANPPPConnection:1",
    )
    request_template = "\r\n".join(
        [
            "M-SEARCH * HTTP/1.1",
            "HOST: 239.255.255.250:1900",
            'MAN: "ssdp:discover"',
            "MX: 2",
            "ST: {target}",
            "",
            "",
        ]
    )
    locations: list[str] = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.settimeout(timeout)
        # On a machine with more than one network adapter (VPN, Docker
        # Desktop, WSL2, Hyper-V/VMware virtual switches...), the OS may pick
        # a virtual interface with no path to the real router as the default
        # route for multicast, so the SSDP request never reaches it and this
        # silently "finds no UPnP gateway" even though the router supports
        # it. Force the send out through the same interface used for real
        # LAN/internet traffic instead of leaving it to the OS default.
        local_ip = local_lan_ip()
        if local_ip and local_ip != "127.0.0.1":
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip))
            except OSError:
                pass
        for target in targets:
            sock.sendto(request_template.format(target=target).encode("ascii"), ("239.255.255.250", 1900))
        while True:
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            text = data.decode("utf-8", errors="replace")
            for line in text.splitlines():
                if line.lower().startswith("location:"):
                    locations.append(line.split(":", 1)[1].strip())

    for location in dict.fromkeys(locations):
        gateway = _gateway_from_description(location)
        if gateway:
            return gateway
    return None


def _gateway_from_description(location: str) -> tuple[str, str, str] | None:
    try:
        with urllib.request.urlopen(location, timeout=4) as response:
            data = response.read(1024 * 256)
    except (OSError, urllib.error.URLError, TimeoutError):
        return None
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None

    base_url = _xml_text(root, "URLBase") or location
    router_name = _xml_text(root, "friendlyName") or urllib.parse.urlparse(location).netloc
    for service in root.iter():
        if _strip_ns(service.tag) != "service":
            continue
        service_type = ""
        control = ""
        for child in service:
            name = _strip_ns(child.tag)
            if name == "serviceType":
                service_type = child.text or ""
            elif name == "controlURL":
                control = child.text or ""
        if service_type in {
            "urn:schemas-upnp-org:service:WANIPConnection:1",
            "urn:schemas-upnp-org:service:WANIPConnection:2",
            "urn:schemas-upnp-org:service:WANPPPConnection:1",
        } and control:
            return urllib.parse.urljoin(base_url, control), service_type, router_name
    return None


def _soap(control_url: str, service_type: str, action: str, args: dict[str, str]) -> bytes:
    body_args = "".join(f"<{key}>{_escape_xml(value)}</{key}>" for key, value in args.items())
    body = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        f'<u:{action} xmlns:u="{service_type}">{body_args}</u:{action}>'
        "</s:Body>"
        "</s:Envelope>"
    ).encode("utf-8")
    request = urllib.request.Request(
        control_url,
        data=body,
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{service_type}#{action}"',
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            return response.read(1024 * 128)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        error = _xml_value(detail.encode("utf-8"), "errorDescription") or f"HTTP {exc.code}"
        raise RuntimeError(error) from exc
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(str(exc)) from exc


def _xml_text(root: ET.Element, wanted: str) -> str:
    for node in root.iter():
        if _strip_ns(node.tag) == wanted:
            return (node.text or "").strip()
    return ""


def _xml_value(data: bytes, wanted: str) -> str:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return ""
    return _xml_text(root, wanted)


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _escape_xml(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
