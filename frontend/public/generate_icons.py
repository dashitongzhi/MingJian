#!/usr/bin/env python3
"""Generate PlanAgent icons from SVG."""

from PIL import Image, ImageDraw, ImageFont
import math

def create_icon(size):
    """Create a PlanAgent icon of given size."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Background gradient (simulated with solid color)
    bg_color = (79, 70, 229)  # Indigo
    draw.rounded_rectangle([(0, 0), (size, size)], radius=size//5, fill=bg_color)
    
    # Draw network nodes
    node_positions = [
        (0.25, 0.25), (0.5, 0.25), (0.75, 0.25),
        (0.25, 0.5),  (0.5, 0.5),  (0.75, 0.5),
        (0.25, 0.75), (0.5, 0.75), (0.75, 0.75)
    ]
    
    # Draw connections
    for i in range(len(node_positions)):
        for j in range(i+1, len(node_positions)):
            x1, y1 = node_positions[i]
            x2, y2 = node_positions[j]
            # Only connect adjacent nodes
            if (abs(x1 - x2) <= 0.25 and abs(y1 - y2) == 0) or \
               (abs(y1 - y2) <= 0.25 and abs(x1 - x2) == 0):
                draw.line(
                    [(int(x1 * size), int(y1 * size)), 
                     (int(x2 * size), int(y2 * size))],
                    fill=(255, 255, 255, 180),
                    width=max(1, size // 50)
                )
    
    # Draw nodes
    node_radius = size // 15
    for i, (x, y) in enumerate(node_positions):
        cx, cy = int(x * size), int(y * size)
        # Central node is larger
        r = node_radius * 1.3 if i == 4 else node_radius
        draw.ellipse([(cx-r, cy-r), (cx+r, cy+r)], fill=(255, 255, 255, 230))
        # Inner circle for central node
        if i == 4:
            r2 = r * 0.5
            draw.ellipse([(cx-r2, cy-r2), (cx+r2, cy+r2)], fill=bg_color)
    
    return img

def main():
    # Generate different sizes
    sizes = {
        'favicon-16x16.png': 16,
        'favicon-32x32.png': 32,
        'apple-touch-icon.png': 180,
        'icon-192.png': 192,
        'icon-512.png': 512,
    }
    
    for filename, size in sizes.items():
        img = create_icon(size)
        img.save(filename)
        print(f'Created {filename} ({size}x{size})')
    
    # Create ICO file with multiple sizes
    ico_sizes = [16, 32, 48]
    ico_images = [create_icon(s) for s in ico_sizes]
    ico_images[0].save(
        'favicon.ico',
        format='ICO',
        sizes=[(s, s) for s in ico_sizes],
        append_images=ico_images[1:]
    )
    print('Created favicon.ico')

if __name__ == '__main__':
    main()