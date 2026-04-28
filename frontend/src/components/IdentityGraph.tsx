import { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import type { GraphNode, GraphEdge } from '../api'

interface Props {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

const RELATION_COLOR: Record<string, string> = {
  SUPPORTS: '#10b981',
  CONTRADICTS: '#f43f5e',
  REFINES: '#3b82f6',
  DERIVES_FROM: '#94a3b8',
}

export default function IdentityGraph({ nodes, edges }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!svgRef.current) return
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const { width, height } = svgRef.current.getBoundingClientRect()
    const W = width || 600
    const H = height || 400

    if (nodes.length === 0) {
      svg.append('text')
        .attr('x', W / 2).attr('y', H / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', '#475569')
        .attr('font-size', 12)
        .text('No identity beliefs yet')
      return
    }

    const simulation = d3.forceSimulation(nodes as d3.SimulationNodeDatum[])
      .force('link', d3.forceLink(edges).id((d: unknown) => (d as GraphNode).id).distance(100))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(W / 2, H / 2))
      .force('collision', d3.forceCollide(30))

    const g = svg.append('g')

    // Arrow markers
    const defs = svg.append('defs')
    Object.entries(RELATION_COLOR).forEach(([rel, color]) => {
      defs.append('marker')
        .attr('id', `arrow-${rel}`)
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 22)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', color)
    })

    // Zoom
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 3])
      .on('zoom', (e) => g.attr('transform', e.transform))
    svg.call(zoom)

    // Links
    const link = g.append('g').selectAll('line')
      .data(edges)
      .join('line')
      .attr('stroke', (d) => RELATION_COLOR[d.relation] ?? '#475569')
      .attr('stroke-width', (d) => Math.max(1, d.weight))
      .attr('stroke-opacity', 0.7)
      .attr('marker-end', (d) => `url(#arrow-${d.relation})`)

    // Drag handler
    const dragHandler = d3.drag<SVGGElement, GraphNode>()
      .on('start', (e, d) => {
        if (!e.active) simulation.alphaTarget(0.3).restart()
        ;(d as d3.SimulationNodeDatum).fx = e.x
        ;(d as d3.SimulationNodeDatum).fy = e.y
      })
      .on('drag', (e, d) => {
        ;(d as d3.SimulationNodeDatum).fx = e.x
        ;(d as d3.SimulationNodeDatum).fy = e.y
      })
      .on('end', (e, d) => {
        if (!e.active) simulation.alphaTarget(0)
        ;(d as d3.SimulationNodeDatum).fx = null
        ;(d as d3.SimulationNodeDatum).fy = null
      })

    // Node circles
    const node = g.append('g').selectAll<SVGGElement, GraphNode>('g')
      .data(nodes)
      .join('g')
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .call(dragHandler as any)

    node.append('circle')
      .attr('r', (d) => 8 + d.confidence * 10)
      .attr('fill', (d) => `rgba(6, 182, 212, ${0.2 + d.confidence * 0.5})`)
      .attr('stroke', '#06b6d4')
      .attr('stroke-width', 1.5)

    node.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', -14)
      .attr('font-size', 10)
      .attr('fill', '#94a3b8')
      .text((d) => d.content.slice(0, 30) + (d.content.length > 30 ? '…' : ''))

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .style('position', 'fixed')
      .style('background', '#161b27')
      .style('border', '1px solid #1e293b')
      .style('border-radius', '6px')
      .style('padding', '8px 10px')
      .style('font-size', '11px')
      .style('color', '#e2e8f0')
      .style('pointer-events', 'none')
      .style('opacity', 0)
      .style('max-width', '220px')
      .style('z-index', 9999)

    node
      .on('mouseover', (e, d) => {
        tooltip.transition().duration(150).style('opacity', 1)
        tooltip.html(`<strong>${d.content}</strong><br/>conf: ${(d.confidence * 100).toFixed(0)}%`)
          .style('left', (e.clientX + 12) + 'px')
          .style('top', (e.clientY - 10) + 'px')
      })
      .on('mousemove', (e) => {
        tooltip.style('left', (e.clientX + 12) + 'px').style('top', (e.clientY - 10) + 'px')
      })
      .on('mouseout', () => tooltip.transition().duration(150).style('opacity', 0))

    simulation.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as d3.SimulationNodeDatum).x!)
        .attr('y1', (d) => (d.source as d3.SimulationNodeDatum).y!)
        .attr('x2', (d) => (d.target as d3.SimulationNodeDatum).x!)
        .attr('y2', (d) => (d.target as d3.SimulationNodeDatum).y!)

      node.attr('transform', (d) => `translate(${(d as d3.SimulationNodeDatum).x},${(d as d3.SimulationNodeDatum).y})`)
    })

    return () => {
      simulation.stop()
      tooltip.remove()
    }
  }, [nodes, edges])

  return <svg ref={svgRef} style={{ width: '100%', height: '100%' }} />
}
