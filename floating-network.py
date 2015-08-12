#!/usr/bin/env python
import sys
from mininet.cli import CLI
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch, Host, Node
from mininet.link import Intf

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
 
        # Add switch
        self.s2 = self.net.addSwitch('s2', dpid='00000000000000a2')
	
	# Connect root namespace to the switch
	self.root = Node('root', inNamespace=False)
	intf = self.net.addLink(self.root, self.s2).intf1
	self.root.setIP('10.0.0.1/32', intf=intf)

	# Add host
	h2 = self.net.addHost('h2', ip='10.0.0.12/24', mac='00:00:00:00:00:02')
	self.net.addLink(h2, self.s2)

    def run(self):
        self.net.build()
        self.net.start()
        self.s2.cmd('ovs-vsctl set bridge s2 protocols=OpenFlow13')
        self.s2.cmd('ovs-vsctl add-port s2 vxlan2')
        self.s2.cmd('ovs-vsctl set interface vxlan2 type=vxlan option:remote_ip=104.236.158.75 option:key=flow')
	self.root.cmd('route add -net 10.0.0.0/24 dev root-eth0')
        CLI(self.net)
        self.net.stop()


topo = MyTopo(cips=sys.argv[1:])
topo.run()
