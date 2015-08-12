#!/usr/bin/env python
import sys
from mininet.cli import CLI
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch, Host
from mininet.link import Intf

QUAGGA_DIR = '/usr/lib/quagga'
# Must exist and be owned by quagga user (quagga:quagga by default on Ubuntu)
QUAGGA_RUN_DIR = '/var/run/quagga'
CONFIG_DIR = 'configs'

class SdnIpHost(Host):
    def __init__(self, name, ip, route, *args, **kwargs):
        Host.__init__(self, name, ip=ip, *args, **kwargs)
        self.route = route

    def config(self, **kwargs):
        Host.config(self, **kwargs)
        self.cmd('ip route add default via %s' % self.route)

class Router(Host):
    def __init__(self, name, quaggaConfFile, zebraConfFile, intfDict, *args, **kwargs):
        Host.__init__(self, name, *args, **kwargs)
        self.quaggaConfFile = quaggaConfFile
        self.zebraConfFile = zebraConfFile
        self.intfDict = intfDict

    def config(self, **kwargs):
        Host.config(self, **kwargs)
        self.cmd('sysctl net.ipv4.ip_forward=1')
        for intf, attrs in self.intfDict.items():
            self.cmd('ip addr flush dev %s' % intf)
            if 'mac' in attrs:
                self.cmd('ip link set %s down' % intf)
                self.cmd('ip link set %s address %s' % (intf, attrs['mac']))
                self.cmd('ip link set %s up ' % intf)
            for addr in attrs['ipAddrs']:
                self.cmd('ip addr add %s dev %s' % (addr, intf))
        self.cmd('/usr/lib/quagga/zebra -d -f %s -z %s/zebra%s.api -i %s/zebra%s.pid' % (self.zebraConfFile, QUAGGA_RUN_DIR, self.name, QUAGGA_RUN_DIR, self.name))
        self.cmd('/usr/lib/quagga/bgpd -d -f %s -z %s/zebra%s.api -i %s/bgpd%s.pid' % (self.quaggaConfFile, QUAGGA_RUN_DIR, self.name, QUAGGA_RUN_DIR, self.name))

    def terminate(self):
        self.cmd("ps ax | egrep 'bgpd%s.pid|zebra%s.pid' | awk '{print $1}' | xargs kill" % (self.name, self.name))
        Host.terminate(self)
 
class MyTopo(object):
    def __init__(self, cname='onos', cips=['10.0.3.1']):
        # Create network with multiple controllers
        self.net = Mininet(controller=RemoteController, switch=OVSKernelSwitch,
                           build=False)
 
        # Add controllers with input IPs to the network
        ctrls = [RemoteController(cname, cip, 6633) for cip in cips]
        for ctrl in ctrls:
            print ctrl.ip
            self.net.addController(ctrl)
 
        # Add switches
        self.s1 = self.net.addSwitch('s1', dpid='00000000000000a1')
        self.s2 = self.net.addSwitch('s2', dpid='00000000000000a2')

	# Set up the internal BGP speaker
	zebraConf = '%s/zebra.conf' % CONFIG_DIR
	bgpEth0 = { 'mac': '00:00:00:00:00:01',
		    'ipAddrs': ['10.0.0.101/24', '192.168.1.1/24'] }
	bgpEth1 = { 'ipAddrs': ['10.10.10.1/24'] }
	bgpIntf = { 'bgp-eth0': bgpEth0, 'bgp-eth1': bgpEth1 }
	bgp = self.net.addHost( "bgp", cls=Router,
			     quaggaConfFile = '%s/quagga-sdn.conf' % CONFIG_DIR,
			     zebraConfFile = zebraConf,
			     intfDict=bgpIntf)
        h1 = self.net.addHost('h1', cls=SdnIpHost, ip='192.168.1.10/24', route='192.168.1.1')
        h2 = self.net.addHost('h2', ip='192.168.1.11/24')
	self.net.addLink(bgp, self.s1)
	self.net.addLink(h1, self.s1)
	self.net.addLink(h2, self.s1)

	# Connect BGP speaker to root namespace so it can peer with ONOS
	root = self.net.addHost('root', inNamespace=False, ip='10.10.10.2/24')
	self.net.addLink(root, bgp)

	# Set up external BGP router
        extEth0 = { 'mac': '00:00:00:00:00:02',
                    'ipAddrs': ['10.0.0.1/24'] }
        extEth1 = { 'ipAddrs': ['192.168.0.1/24'] }
        extIntf = { 'ext-eth0': extEth0, 'ext-eth1': extEth1 }
        ext = self.net.addHost( "ext", cls=Router,
                             quaggaConfFile = '%s/quagga-ext.conf' % CONFIG_DIR,
                             zebraConfFile = zebraConf,
                             intfDict=extIntf)
        h3 = self.net.addHost('h3', cls=SdnIpHost, ip='192.168.0.10/24', route='192.168.0.1')
        self.net.addLink(ext, self.s2)
        self.net.addLink(ext, h3)

	self.net.addLink(self.s1, self.s2)

    def run(self):
        self.net.build()
        self.net.start()
        CLI(self.net)
        self.net.stop()


topo = MyTopo(cips=sys.argv[1:])
topo.run()
