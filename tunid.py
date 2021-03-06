#!/usr/bin/env python
import sys
from mininet.cli import CLI
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
 
class MyTopo(object):
    def __init__(self, cname='onos', cips=['10.0.3.1']):
        # Create network with multiple controllers
        self.net = Mininet(controller=RemoteController, switch=OVSKernelSwitch,
                           build=False, autoSetMacs=True)
 
        # Add controllers with input IPs to the network
        ctrls = [RemoteController(cname, cip, 6633) for cip in cips]
        for ctrl in ctrls:
            print ctrl.ip
            self.net.addController(ctrl)
 
        # Add components
        self.s1 = self.net.addSwitch('s1', protocols='OpenFlow13')
        h1 = self.net.addHost('h1', ip='192.168.0.9', mac='00:00:00:00:00:01')
        h2 = self.net.addHost('h2', ip='192.168.0.10', mac='00:00:00:00:00:02')

        # Add links
        self.net.addLink(h1, self.s1)
        self.net.addLink(h2, self.s1)
 
    def run(self):
        self.net.build()
        self.net.start()
	self.s1.cmd('ovs-vsctl set bridge s1 protocols=OpenFlow13')
        self.s1.cmd('ovs-vsctl add-port s1 vxlan1')
        self.s1.cmd('ovs-vsctl set interface vxlan1 type=vxlan option:remote_ip=flow option:local_ip=flow option:key=flow')
        CLI(self.net)
        self.net.stop()
 
topo = MyTopo(cips=sys.argv[1:])
topo.run()
