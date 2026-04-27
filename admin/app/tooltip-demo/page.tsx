'use client';

import React from 'react';
import Tooltip from '../components/Tooltip';

export default function TooltipDemoPage() {
  return (
    <div className="container mx-auto p-8 space-y-12">
      <h1 className="text-3xl font-bold mb-8">Tooltip Demo</h1>
      
      {/* Basic Tooltips */}
      <section className="space-y-6">
        <h2 className="text-xl font-semibold">Basic Tooltips</h2>
        <div className="flex gap-4 flex-wrap">
          <Tooltip content="This is a simple tooltip">
            <button className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
              Hover me
            </button>
          </Tooltip>
          
          <Tooltip content="Tooltip with custom delay" delay={1000}>
            <button className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600">
              Slow tooltip (1s delay)
            </button>
          </Tooltip>
          
          <Tooltip content="Instant tooltip" delay={0}>
            <button className="px-4 py-2 bg-purple-500 text-white rounded hover:bg-purple-600">
              Instant tooltip
            </button>
          </Tooltip>
        </div>
      </section>

      {/* Positioning */}
      <section className="space-y-6">
        <h2 className="text-xl font-semibold">Manual Positioning</h2>
        <div className="grid grid-cols-2 gap-8 max-w-md mx-auto">
          <div className="text-center">
            <Tooltip content="Top positioned tooltip" position="top">
              <button className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600">
                Top
              </button>
            </Tooltip>
          </div>
          
          <div className="text-center">
            <Tooltip content="Bottom positioned tooltip" position="bottom">
              <button className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
                Bottom
              </button>
            </Tooltip>
          </div>
          
          <div className="text-center">
            <Tooltip content="Left positioned tooltip" position="left">
              <button className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600">
                Left
              </button>
            </Tooltip>
          </div>
          
          <div className="text-center">
            <Tooltip content="Right positioned tooltip" position="right">
              <button className="px-4 py-2 bg-yellow-500 text-white rounded hover:bg-yellow-600">
                Right
              </button>
            </Tooltip>
          </div>
        </div>
      </section>

      {/* Auto-positioning */}
      <section className="space-y-6">
        <h2 className="text-xl font-semibold">Auto-positioning (Smart Placement)</h2>
        <div className="grid grid-cols-4 gap-4">
          {/* Corner elements to test auto-positioning */}
          <div className="text-left">
            <Tooltip content="Auto-positioned tooltip that avoids window edges" position="auto">
              <button className="px-3 py-2 bg-indigo-500 text-white rounded hover:bg-indigo-600 text-sm">
                Top-left corner
              </button>
            </Tooltip>
          </div>
          
          <div className="col-span-2 text-center">
            <Tooltip content="This tooltip will position itself optimally" position="auto">
              <button className="px-4 py-2 bg-pink-500 text-white rounded hover:bg-pink-600">
                Center element
              </button>
            </Tooltip>
          </div>
          
          <div className="text-right">
            <Tooltip content="Smart positioning prevents overflow" position="auto">
              <button className="px-3 py-2 bg-teal-500 text-white rounded hover:bg-teal-600 text-sm">
                Top-right corner
              </button>
            </Tooltip>
          </div>
        </div>
      </section>

      {/* Complex Content */}
      <section className="space-y-6">
        <h2 className="text-xl font-semibold">Complex Content</h2>
        <div className="flex gap-4 flex-wrap">
          <Tooltip 
            content={
              <div className="space-y-2">
                <div className="font-semibold">User Information</div>
                <div className="text-sm">
                  <div>Name: John Doe</div>
                  <div>Email: john@example.com</div>
                  <div>Role: Administrator</div>
                </div>
              </div>
            }
          >
            <div className="flex items-center gap-2 p-3 border rounded-lg cursor-pointer hover:bg-gray-50">
              <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center text-white text-sm font-semibold">
                JD
              </div>
              <span>Hover for user details</span>
            </div>
          </Tooltip>
          
          <Tooltip 
            content={
              <div className="space-y-1">
                <div className="font-medium text-green-200">✓ All systems operational</div>
                <div className="text-xs text-gray-300">Last updated: 2 minutes ago</div>
              </div>
            }
          >
            <div className="flex items-center gap-2 p-3 border rounded-lg cursor-pointer hover:bg-gray-50">
              <div className="w-3 h-3 bg-green-500 rounded-full"></div>
              <span>System Status</span>
            </div>
          </Tooltip>
        </div>
      </section>

      {/* Different Trigger Elements */}
      <section className="space-y-6">
        <h2 className="text-xl font-semibold">Different Trigger Elements</h2>
        <div className="flex gap-6 flex-wrap items-center">
          <Tooltip content="Tooltip on text">
            <span className="text-blue-600 underline cursor-help">
              Hover this text
            </span>
          </Tooltip>
          
          <Tooltip content="Icon with helpful information">
            <div className="w-6 h-6 bg-gray-400 rounded-full flex items-center justify-center text-white text-sm cursor-help">
              ?
            </div>
          </Tooltip>
          
          <Tooltip content="This input has a tooltip">
            <input 
              type="text" 
              placeholder="Hover me"
              className="px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </Tooltip>
          
          <Tooltip content="Disabled tooltip example" disabled>
            <button className="px-4 py-2 bg-gray-400 text-white rounded cursor-not-allowed">
              Disabled tooltip
            </button>
          </Tooltip>
        </div>
      </section>

      {/* Edge Cases */}
      <section className="space-y-6">
        <h2 className="text-xl font-semibold">Edge Cases & Behavior</h2>
        <div className="space-y-4">
          <div className="text-sm text-gray-600 space-y-2">
            <p>• Tooltips automatically reposition to avoid window edges</p>
            <p>• Click outside the tooltip to dismiss it</p>
            <p>• Tooltips hide on scroll and window resize</p>
            <p>• Focus and blur events also trigger tooltips</p>
            <p>• Hover delay can be customized per tooltip</p>
          </div>
          
          <div className="flex gap-4">
            <Tooltip content="Try scrolling or resizing the window while this is open">
              <button className="px-4 py-2 bg-orange-500 text-white rounded hover:bg-orange-600">
                Test scroll/resize behavior
              </button>
            </Tooltip>
            
            <Tooltip content="This tooltip can be focused with keyboard navigation">
              <button className="px-4 py-2 bg-cyan-500 text-white rounded hover:bg-cyan-600 focus:ring-2 focus:ring-cyan-300">
                Keyboard accessible
              </button>
            </Tooltip>
          </div>
        </div>
      </section>
    </div>
  );
}