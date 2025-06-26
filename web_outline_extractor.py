#!/usr/bin/env python3
"""
Website Outline Extractor

This module provides functionality to extract heading structure and table of contents
from websites using BeautifulSoup. Designed to handle large single-page websites
efficiently and provide dual output formats for both human reading and AI consumption.
"""

import time
import json
import os
import re
import argparse
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup


def fetch_webpage(url: str) -> tuple[str, BeautifulSoup]:
    """
    Fetch webpage content and return both raw HTML and parsed soup.
    
    Args:
        url (str): URL of the website to fetch
        
    Returns:
        tuple[str, BeautifulSoup]: Raw HTML content and parsed BeautifulSoup object
        
    Raises:
        requests.RequestException: If the website cannot be accessed
        Exception: If the HTML cannot be parsed
    """
    print(f"Fetching content from {url}...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Parse HTML content
        soup = BeautifulSoup(response.content, 'lxml')
        
        return response.text, soup
        
    except requests.RequestException as e:
        raise requests.RequestException(f"Error fetching website {url}: {str(e)}")
    except Exception as e:
        raise Exception(f"Error parsing HTML from {url}: {str(e)}")


def extract_headings_from_soup(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    Extract heading structure from parsed HTML soup.
    
    This function analyzes the parsed HTML and extracts the heading hierarchy (h1-h6)
    to create a structured outline similar to PDF bookmarks.
    
    Args:
        soup (BeautifulSoup): Parsed HTML soup object
        
    Returns:
        List[Dict[str, Any]]: List of heading dictionaries containing:
            - title (str): Heading text content
            - level (int): Heading level (1-6 for h1-h6)
            - tag (str): HTML tag name (h1, h2, etc.)
            - id (str): Element ID if available
            - content (str): 50-word preview of section content
            - reference_key (str): Unique reference for Claude Code lookup
            - hierarchical_path (List[str]): Full path to this heading
            - search_variants (List[str]): Alternative search terms
    """
    start_time = time.time()
    
    # Extract all headings (h1-h6)
    heading_tags = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    
    headings = []
    level_counters = [0, 0, 0, 0, 0, 0]  # Track heading counts per level
    hierarchical_stack = []  # Track current path
    
    for i, heading in enumerate(heading_tags):
        # Extract heading text and clean it
        title = clean_heading_text(heading.get_text())
        
        if title:  # Only include non-empty headings
            # Get heading level from tag name
            level = int(heading.name[1])  # h1 -> 1, h2 -> 2, etc.
            
            # Update level counters and hierarchical stack
            level_counters[level-1] += 1
            # Reset counters for deeper levels
            for j in range(level, 6):
                if j > level-1:
                    level_counters[j] = 0
            
            # Update hierarchical stack
            hierarchical_stack = hierarchical_stack[:level-1]  # Keep only parent levels
            hierarchical_stack.append(title)
            
            # Get element ID if available
            heading_id = heading.get('id', '')
            
            # Extract content preview for this section
            next_headings = heading_tags[i+1:] if i+1 < len(heading_tags) else []
            content_preview = extract_section_content(heading, next_headings)
            
            # Generate reference key
            reference_key = f"[{level}.{level_counters[level-1]}] {title}"
            
            # Generate search variants
            search_variants = generate_search_variants(title)
            
            heading_data = {
                'title': title,
                'level': level,
                'tag': heading.name,
                'id': heading_id,
                'content': content_preview,
                'reference_key': reference_key,
                'hierarchical_path': hierarchical_stack.copy(),
                'search_variants': search_variants
            }
            headings.append(heading_data)
    
    # Calculate total processing time
    processing_time = time.time() - start_time
    print(f"Extracted {len(headings)} headings with enhanced references in {processing_time:.2f} seconds")
    
    return headings


def extract_headings(url: str) -> List[Dict[str, Any]]:
    """
    Extract heading structure from a website (legacy wrapper function).
    
    This function maintains backward compatibility while using the new
    fetch-once-analyze-locally approach internally.
    
    Args:
        url (str): URL of the website to extract headings from
        
    Returns:
        List[Dict[str, Any]]: List of heading dictionaries
        
    Raises:
        requests.RequestException: If the website cannot be accessed
        Exception: If the HTML cannot be parsed
    """
    try:
        # Fetch webpage content once
        raw_html, soup = fetch_webpage(url)
        
        # Extract headings from parsed content
        return extract_headings_from_soup(soup)
        
    except (requests.RequestException, Exception):
        # Re-raise the original exceptions for backward compatibility
        raise


def extract_section_content(heading_element, next_headings: List) -> str:
    """
    Extract content between this heading and the next heading.
    
    Args:
        heading_element: BeautifulSoup heading element
        next_headings: List of subsequent heading elements
        
    Returns:
        str: 50-word preview of section content with image tags replaced
    """
    # Find the next heading element to know where to stop
    stop_element = next_headings[0] if next_headings else None
    
    # Collect all text content between this heading and the next
    content_elements = []
    current = heading_element.next_sibling
    
    while current and current != stop_element:
        if hasattr(current, 'get_text'):
            # This is a tag, extract text content
            text_content = current.get_text(strip=True)
            if text_content:
                content_elements.append(text_content)
        elif isinstance(current, str) and current.strip():
            # This is direct text content
            content_elements.append(current.strip())
        
        current = current.next_sibling
    
    # Join all content and clean it
    full_content = ' '.join(content_elements)
    
    # Replace image references with descriptive tags
    full_content = replace_images_with_tags(full_content)
    
    # Truncate to 50 words
    return truncate_to_words(full_content, 50)


def replace_images_with_tags(text: str) -> str:
    """
    Replace image references with descriptive tags.
    
    Args:
        text (str): Text content that may contain image references
        
    Returns:
        str: Text with image references replaced by [IMAGE: filename] tags
    """
    # Find common image file extensions in text
    image_pattern = r'([a-zA-Z0-9_-]+\.(jpg|jpeg|png|gif|svg|webp|bmp))'
    
    def replace_match(match):
        filename = match.group(1)
        # Extract just the base name without extension for readability
        base_name = filename.split('.')[0]
        return f"[IMAGE: {base_name}]"
    
    return re.sub(image_pattern, replace_match, text, flags=re.IGNORECASE)


def truncate_to_words(text: str, word_limit: int) -> str:
    """
    Truncate text to a specific number of words.
    
    Args:
        text (str): Text to truncate
        word_limit (int): Maximum number of words to keep
        
    Returns:
        str: Truncated text with ellipsis if needed
    """
    if not text:
        return ""
    
    # Clean and normalize whitespace
    cleaned_text = re.sub(r'\s+', ' ', text.strip())
    
    # Split into words
    words = cleaned_text.split()
    
    # Return truncated version if necessary
    if len(words) <= word_limit:
        return cleaned_text
    else:
        truncated = ' '.join(words[:word_limit])
        return f"{truncated}..."


def generate_search_variants(title: str) -> List[str]:
    """
    Generate search variants for a heading title.
    
    This function creates alternative search terms that users might use
    to find this section, improving search flexibility.
    
    Args:
        title (str): Original heading title
        
    Returns:
        List[str]: List of search variant strings
    """
    if not title:
        return []
    
    variants = []
    
    # Add the original title
    variants.append(title.lower())
    
    # Add version without common prefixes
    title_lower = title.lower()
    prefixes_to_remove = ['chapter ', 'part ', 'section ', 'quick reference: ', 'optional rule: ']
    for prefix in prefixes_to_remove:
        if title_lower.startswith(prefix):
            variants.append(title_lower[len(prefix):])
    
    # Add acronyms if title has multiple words
    words = title.split()
    if len(words) > 1:
        # Create acronym from first letters
        acronym = ''.join(word[0].lower() for word in words if word)
        if len(acronym) > 1:
            variants.append(acronym)
    
    # Add version without special characters
    no_special = re.sub(r'[^\w\s]', '', title.lower())
    if no_special != title.lower():
        variants.append(no_special)
    
    # Add individual significant words (longer than 3 characters)
    significant_words = [word.lower() for word in words if len(word) > 3]
    variants.extend(significant_words)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_variants = []
    for variant in variants:
        if variant not in seen and variant.strip():
            seen.add(variant)
            unique_variants.append(variant)
    
    return unique_variants


def clean_heading_text(text: str) -> str:
    """
    Clean and normalize heading text.
    
    This helper function removes extra whitespace, newlines, and other
    formatting artifacts from heading text.
    
    Args:
        text (str): Raw heading text
        
    Returns:
        str: Cleaned heading text
    """
    if not text:
        return ""
    
    # Remove extra whitespace and newlines
    cleaned = re.sub(r'\s+', ' ', text.strip())
    
    # Remove common artifacts
    cleaned = cleaned.replace('\n', ' ').replace('\t', ' ')
    
    return cleaned.strip()


def save_headings_json(headings: List[Dict[str, Any]], output_path: str, source_url: str) -> bool:
    """
    Save extracted headings to a JSON file.
    
    This function saves the heading data in JSON format, which is ideal
    for Claude to consume as context. The JSON preserves all structure
    and metadata efficiently.
    
    Args:
        headings (List[Dict]): List of heading dictionaries
        output_path (str): Path where to save the JSON file
        source_url (str): Original URL that was processed
        
    Returns:
        bool: True if saved successfully, False otherwise
    """
    try:
        # Add metadata to the JSON output
        output_data = {
            "metadata": {
                "source_url": source_url,
                "extraction_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_headings": len(headings),
                "format_version": "2.0",
                "claude_code_usage": {
                    "lookup_command": "python find_section.py \"<search_term>\" --json-file <this_filename>",
                    "search_options": {
                        "--by-id": "Search by element ID (e.g., 'table-of-contents')",
                        "--fuzzy": "Enable fuzzy matching for typos",
                        "--all-matches": "Show all sections matching the search term",
                        "--show-content": "Display full content preview",
                        "--show-context": "Show parent section context"
                    },
                    "examples": [
                        "python find_section.py \"[2.1] Table of Contents\" --json-file headings.json",
                        "python find_section.py \"Character Stats\" --json-file headings.json --fuzzy",
                        "python find_section.py \"combat\" --json-file headings.json --all-matches"
                    ]
                }
            },
            "headings": headings
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"Headings saved to {output_path}")
        return True
        
    except Exception as e:
        print(f"Error saving headings to JSON: {e}")
        return False


def save_headings_markdown(headings: List[Dict[str, Any]], output_path: str, source_url: str) -> bool:
    """
    Save extracted headings to a Markdown file.
    
    This function saves the heading data in Markdown format with proper
    hierarchical structure using headers for easy reading.
    
    Args:
        headings (List[Dict]): List of heading dictionaries
        output_path (str): Path where to save the Markdown file
        source_url (str): Original URL that was processed
        
    Returns:
        bool: True if saved successfully, False otherwise
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            # Write header
            f.write("# Website Heading Outline\n\n")
            f.write(f"**Source**: {source_url}\n")
            f.write(f"**Generated on**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Total headings**: {len(headings)}\n\n")
            f.write("---\n\n")
            
            # Write headings with proper markdown formatting
            for heading in headings:
                level = heading.get('level', 1)
                title = heading.get('title', 'Untitled').strip()
                heading_id = heading.get('id', '')
                content = heading.get('content', '')
                
                # Create markdown headers based on level
                markdown_level = '#' * (level + 1)  # h1 -> ##, h2 -> ###, etc.
                f.write(f"{markdown_level} {title}\n")
                
                if heading_id:
                    f.write(f"*ID: {heading_id}*\n")
                
                # Add content preview if available
                if content:
                    f.write(f"\n*Content preview:* {content}\n")
                
                f.write("\n")
            
            # Add table of contents at the end
            f.write("---\n\n")
            f.write("## Quick Reference\n\n")
            f.write("| Level | Heading | ID |\n")
            f.write("|-------|---------|----|\n")
            
            # Show all headings in quick reference
            for heading in headings:
                level = heading.get('level', 1)
                title = heading.get('title', 'Untitled').strip()
                heading_id = heading.get('id', '')
                level_indicator = "  " * (level - 1) + f"H{level}"
                f.write(f"| {level_indicator} | {title} | {heading_id} |\n")
        
        print(f"Headings saved to {output_path}")
        return True
        
    except Exception as e:
        print(f"Error saving headings to Markdown: {e}")
        return False


def save_headings_html(headings: List[Dict[str, Any]], output_path: str, source_url: str) -> bool:
    """
    Save extracted headings to an HTML file.
    
    This function saves the heading data in HTML format with proper
    hierarchical structure and styling for web viewing and sharing.
    
    Args:
        headings (List[Dict]): List of heading dictionaries
        output_path (str): Path where to save the HTML file
        source_url (str): Original URL that was processed
        
    Returns:
        bool: True if saved successfully, False otherwise
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            # Write HTML header with CSS styling
            f.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Website Heading Outline</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
        }
        .header {
            border-bottom: 2px solid #e1e5e9;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        .metadata {
            color: #666;
            font-size: 0.9em;
            margin-bottom: 10px;
        }
        .outline {
            margin-bottom: 40px;
        }
        .heading {
            margin: 8px 0;
            padding: 4px 0;
            position: relative;
        }
        .heading-title {
            font-weight: 500;
            color: #2c3e50;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .reference-key {
            color: #6c757d;
            font-weight: 600;
            font-size: 0.9em;
            background-color: #f8f9fa;
            padding: 2px 6px;
            border-radius: 4px;
            border: 1px solid #e9ecef;
        }
        .heading-text {
            flex: 1;
        }
        .heading-id {
            color: #7f8c8d;
            font-style: italic;
            font-size: 0.85em;
        }
        .copy-btn {
            background-color: #007bff;
            color: white;
            border: none;
            padding: 4px 8px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.8em;
            opacity: 0.7;
            transition: opacity 0.2s;
        }
        .copy-btn:hover {
            opacity: 1;
            background-color: #0056b3;
        }
        .copy-btn:active {
            background-color: #004085;
        }
        .content-preview {
            color: #555;
            margin-top: 4px;
            font-size: 0.9em;
            line-height: 1.4;
        }
        .level-1 { margin-left: 0px; font-size: 1.4em; font-weight: 600; color: #1a202c; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 12px; }
        .level-2 { margin-left: 20px; font-size: 1.2em; font-weight: 500; margin-bottom: 8px; }
        .level-3 { margin-left: 40px; font-size: 1.1em; font-weight: 500; }
        .level-4 { margin-left: 60px; font-size: 1em; color: #4a5568; }
        .level-5 { margin-left: 80px; font-size: 0.95em; color: #718096; }
        .level-6 { margin-left: 100px; font-size: 0.9em; color: #a0aec0; }
        .quick-ref {
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 6px;
            padding: 20px;
            margin-top: 30px;
        }
        .quick-ref h2 {
            margin-top: 0;
            color: #495057;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        .ref-table th, .ref-table td {
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid #dee2e6;
        }
        .ref-table th {
            background-color: #f8f9fa;
            font-weight: 600;
            color: #495057;
        }
        .ref-table tr:hover {
            background-color: #f8f9fa;
        }
        .source-link {
            color: #007bff;
            text-decoration: none;
        }
        .source-link:hover {
            text-decoration: underline;
        }
        .usage-info {
            background-color: #e7f3ff;
            border: 1px solid #b8daff;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 20px;
        }
        .usage-info h3 {
            margin-top: 0;
            color: #004085;
        }
        .usage-info code {
            background-color: #f8f9fa;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Monaco', 'Consolas', monospace;
        }
    </style>
    <script>
        function copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(function() {
                // Visual feedback - could add a toast notification here
                console.log('Copied to clipboard: ' + text);
            }, function(err) {
                console.error('Failed to copy: ', err);
            });
        }
    </script>
</head>
<body>
""")
            
            # Write header section
            f.write('<div class="header">\n')
            f.write('<h1>Website Heading Outline</h1>\n')
            f.write(f'<div class="metadata">Source: <a href="{source_url}" class="source-link" target="_blank">{source_url}</a></div>\n')
            f.write(f'<div class="metadata">Generated on: {time.strftime("%Y-%m-%d %H:%M:%S")}</div>\n')
            f.write(f'<div class="metadata">Total headings: {len(headings)}</div>\n')
            f.write('</div>\n\n')
            
            # Write usage information
            f.write('<div class="usage-info">\n')
            f.write('<h3>🔍 Claude Code Usage</h3>\n')
            f.write('<p>Copy any reference key (like <code>[2.1] Table of Contents</code>) and use with:</p>\n')
            f.write('<p><code>python find_section.py "[2.1] Table of Contents" --json-file headings.json</code></p>\n')
            f.write('<p>Click the 📋 buttons to copy reference keys directly.</p>\n')
            f.write('</div>\n\n')
            
            # Write main outline
            f.write('<div class="outline">\n')
            for heading in headings:
                level = heading.get('level', 1)
                title = heading.get('title', 'Untitled').strip()
                heading_id = heading.get('id', '')
                content = heading.get('content', '')
                reference_key = heading.get('reference_key', '')
                
                # Ensure level doesn't exceed our CSS classes
                css_level = min(level, 6)
                
                f.write(f'<div class="heading level-{css_level}">\n')
                f.write('  <div class="heading-title">\n')
                
                # Add reference key
                if reference_key:
                    f.write(f'    <span class="reference-key">{reference_key}</span>\n')
                
                # Add the main title text
                f.write(f'    <span class="heading-text">{title}</span>\n')
                
                # Add heading ID
                if heading_id:
                    f.write(f'    <span class="heading-id">#{heading_id}</span>\n')
                
                # Add copy button
                if reference_key:
                    copy_text = reference_key
                    f.write(f'    <button class="copy-btn" onclick="copyToClipboard(\'{copy_text}\')">📋</button>\n')
                
                f.write('  </div>\n')
                
                # Add content preview if available
                if content:
                    f.write(f'  <div class="content-preview">{content}</div>\n')
                
                f.write('</div>\n')
            f.write('</div>\n\n')
            
            # Write quick reference section
            f.write('<div class="quick-ref">\n')
            f.write('<h2>Quick Reference</h2>\n')
            f.write('<table class="ref-table">\n')
            f.write('<thead>\n')
            f.write('<tr><th>Reference Key</th><th>Title</th><th>Element ID</th><th>Copy</th></tr>\n')
            f.write('</thead>\n')
            f.write('<tbody>\n')
            
            # Show all headings in quick reference
            for heading in headings:
                reference_key = heading.get('reference_key', '')
                title = heading.get('title', 'Untitled').strip()
                heading_id = heading.get('id', '')
                
                f.write('<tr>')
                f.write(f'<td>{reference_key}</td>')
                f.write(f'<td>{title}</td>')
                f.write(f'<td>{heading_id}</td>')
                if reference_key:
                    f.write(f'<td><button class="copy-btn" onclick="copyToClipboard(\'{reference_key}\')">📋</button></td>')
                else:
                    f.write('<td></td>')
                f.write('</tr>\n')
            
            f.write('</tbody>\n')
            f.write('</table>\n')
            f.write('</div>\n\n')
            
            # Close HTML
            f.write('</body>\n</html>\n')
        
        print(f"Headings saved to {output_path}")
        return True
        
    except Exception as e:
        print(f"Error saving headings to HTML: {e}")
        return False


def print_heading_outline(headings: List[Dict[str, Any]]) -> None:
    """
    Print heading outline in a readable hierarchical format.
    
    This utility function displays the extracted headings in a clean,
    indented format that shows the hierarchical structure.
    
    Args:
        headings (List[Dict]): List of heading dictionaries
    """
    if not headings:
        print("No headings found.")
        return
        
    print(f"\nHeading Outline ({len(headings)} headings):")
    print("-" * 50)
    
    for heading in headings:
        level = heading.get('level', 1)
        title = heading.get('title', 'Untitled')
        tag = heading.get('tag', 'h?')
        heading_id = heading.get('id', '')
        
        indent = "  " * (level - 1)
        id_text = f" (#{heading_id})" if heading_id else ""
        print(f"{indent}{tag.upper()}: {title}{id_text}")


def download_full_website(url: str, output_dir: str) -> str:
    """
    Download complete website using wget.
    
    Args:
        url (str): URL to download
        output_dir (str): Directory to save downloaded files
        
    Returns:
        str: Path to main HTML file
        
    Raises:
        Exception: If wget fails or files cannot be found
    """
    import subprocess
    import tempfile
    from pathlib import Path
    
    print(f"Downloading complete website from {url}...")
    
    try:
        # Run wget command to download complete website
        wget_cmd = [
            'wget',
            '--mirror',
            '--convert-links',
            '--adjust-extension',
            '--page-requisites',
            '--no-parent',
            '--directory-prefix', output_dir,
            '--user-agent', 'Mozilla/5.0 (compatible; WebExtractor)',
            '--timeout', '30',
            '--tries', '3',
            url
        ]
        
        print(f"Running wget command...")
        result = subprocess.run(wget_cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            raise Exception(f"wget failed: {result.stderr}")
        
        # Find the main HTML file in downloaded structure
        download_path = Path(output_dir)
        html_files = list(download_path.rglob("*.html"))
        
        if not html_files:
            raise Exception("No HTML files found in downloaded website")
        
        # Find the main index file (prefer index.html, or use first HTML file)
        main_html = None
        for html_file in html_files:
            if html_file.name.lower() in ['index.html', 'main.html', 'home.html']:
                main_html = html_file
                break
        
        if not main_html:
            main_html = html_files[0]  # Use first HTML file found
        
        print(f"Downloaded {len(html_files)} HTML files, main file: {main_html}")
        return str(main_html)
        
    except subprocess.TimeoutExpired:
        raise Exception("wget command timed out (120 seconds)")
    except Exception as e:
        raise Exception(f"Error downloading website: {str(e)}")


def save_headings_full_html(headings: List[Dict[str, Any]], output_path: str, source_url: str, raw_html: Optional[str] = None) -> bool:
    """
    Save enhanced full webpage with copy reference buttons and embedded resources.
    
    This function takes the original webpage and creates a complete, self-contained
    HTML file with all CSS, images, and resources embedded inline, plus adds copy
    reference buttons next to each heading.
    
    Args:
        headings (List[Dict]): List of heading dictionaries with reference keys
        output_path (str): Path where to save the enhanced webpage
        source_url (str): Original URL that was processed
        raw_html (Optional[str]): Raw HTML content (if None, will download fresh)
        
    Returns:
        bool: True if saved successfully, False otherwise
    """
    import base64
    from urllib.parse import urljoin, urlparse
    
    try:
        if raw_html:
            print(f"Using cached HTML content for enhanced webpage...")
            soup = BeautifulSoup(raw_html, 'lxml')
        else:
            print(f"Downloading fresh HTML content...")
            fresh_html, soup = fetch_webpage(source_url)
        
        print(f"Processing webpage to embed all resources...")
        
        # Embed CSS stylesheets inline
        css_links = soup.find_all('link', {'rel': 'stylesheet'})
        for css_link in css_links:
            href = css_link.get('href')
            if href:
                try:
                    css_url = urljoin(source_url, href)
                    print(f"  Downloading CSS: {css_url}")
                    css_response = requests.get(css_url, timeout=30)
                    css_response.raise_for_status()
                    
                    # Create inline style tag with proper media attribute preservation
                    style_tag = soup.new_tag('style')
                    style_tag['type'] = 'text/css'
                    
                    # Preserve media queries and other attributes
                    if css_link.get('media'):
                        style_tag['media'] = css_link.get('media')
                    
                    css_content = css_response.text
                    
                    # Clean up CSS content to prevent text rendering issues
                    css_content = css_content.strip()
                    
                    # Resolve any @import statements in the CSS
                    import_pattern = r'@import\s+(?:url\()?["\']?([^)"\'\s]+)["\']?\)?[^;]*;'
                    imports = re.finditer(import_pattern, css_content, re.IGNORECASE)
                    
                    for import_match in imports:
                        import_url = import_match.group(1)
                        try:
                            full_import_url = urljoin(css_url, import_url)
                            print(f"    Downloading @import CSS: {full_import_url}")
                            import_response = requests.get(full_import_url, timeout=30)
                            import_response.raise_for_status()
                            
                            # Replace @import with the actual CSS content
                            css_content = css_content.replace(import_match.group(0), f"/* Imported from {import_url} */\n{import_response.text}")
                        except Exception as e:
                            print(f"    Failed to import CSS {import_url}: {e}")
                    
                    # Use text content instead of string to avoid HTML escaping issues
                    style_tag.append(css_content)
                    
                    # Insert into head if possible, otherwise replace the link
                    head = soup.find('head')
                    if head:
                        head.append(style_tag)
                        css_link.decompose()  # Remove the original link
                    else:
                        css_link.replace_with(style_tag)
                except Exception as e:
                    print(f"  Failed to embed CSS {href}: {e}")
                    # Keep the original link as fallback
        
        # Also check for any remaining link tags that might have CSS
        other_css_links = soup.find_all('link', href=True)
        for link in other_css_links:
            href = link.get('href', '')
            if '.css' in href.lower() or 'stylesheet' in str(link).lower():
                try:
                    css_url = urljoin(source_url, href)
                    print(f"  Downloading additional CSS: {css_url}")
                    css_response = requests.get(css_url, timeout=30)
                    css_response.raise_for_status()
                    
                    style_tag = soup.new_tag('style')
                    style_tag['type'] = 'text/css'
                    style_tag.append(f"/* From {href} */\n{css_response.text}")
                    
                    # Insert into head if possible
                    head = soup.find('head')
                    if head:
                        head.append(style_tag)
                        link.decompose()
                    else:
                        link.replace_with(style_tag)
                except Exception as e:
                    print(f"  Failed to embed additional CSS {href}: {e}")
        
        # Embed images as base64 data URIs
        images = soup.find_all('img')
        for img in images:
            src = img.get('src')
            if src and not src.startswith('data:'):
                try:
                    img_url = urljoin(source_url, src)
                    print(f"  Downloading image: {img_url}")
                    img_response = requests.get(img_url, timeout=30)
                    img_response.raise_for_status()
                    
                    # Determine image MIME type
                    content_type = img_response.headers.get('content-type', 'image/png')
                    
                    # Convert to base64
                    img_data = base64.b64encode(img_response.content).decode('utf-8')
                    data_uri = f"data:{content_type};base64,{img_data}"
                    
                    # Replace src with data URI
                    img['src'] = data_uri
                except Exception as e:
                    print(f"  Failed to embed image {src}: {e}")
                    # Keep the original src as fallback
        
        # Embed background images in CSS
        style_tags = soup.find_all('style')
        for style_tag in style_tags:
            if style_tag.string:
                try:
                    css_content = style_tag.string
                    # Find background-image URLs
                    import re
                    bg_pattern = r'background-image:\s*url\(["\']?([^)]+)["\']?\)'
                    matches = re.finditer(bg_pattern, css_content)
                    
                    for match in matches:
                        bg_url = match.group(1)
                        if not bg_url.startswith('data:'):
                            try:
                                full_bg_url = urljoin(source_url, bg_url)
                                print(f"  Downloading background image: {full_bg_url}")
                                bg_response = requests.get(full_bg_url, timeout=30)
                                bg_response.raise_for_status()
                                
                                content_type = bg_response.headers.get('content-type', 'image/png')
                                bg_data = base64.b64encode(bg_response.content).decode('utf-8')
                                data_uri = f"data:{content_type};base64,{bg_data}"
                                
                                # Replace in CSS
                                css_content = css_content.replace(f'url({bg_url})', f'url({data_uri})')
                                css_content = css_content.replace(f'url("{bg_url}")', f'url("{data_uri}")')
                                css_content = css_content.replace(f"url('{bg_url}')", f"url('{data_uri}')")
                            except Exception as e:
                                print(f"  Failed to embed background image {bg_url}: {e}")
                    
                    # Clear and update the style content properly
                    style_tag.clear()
                    style_tag.append(css_content)
                except Exception as e:
                    print(f"  Error processing CSS backgrounds: {e}")
        
        # Add CSS to ensure proper color rendering and theme detection
        head = soup.find('head')
        if head:
            # Add CSS to force proper theme variables and ensure visibility
            theme_fix_css = soup.new_tag('style')
            theme_fix_css['type'] = 'text/css'
            theme_css_content = """
                /* Theme and color fixes for offline viewing */
                html, body {
                    background-color: var(--bg-color, #ffffff) !important;
                    color: var(--text-color, #000000) !important;
                }
                
                /* Ensure dark mode CSS variables are defined if missing */
                :root {
                    --bg-color: #ffffff;
                    --text-color: #000000;
                    --link-color: #0066cc;
                    --border-color: #cccccc;
                }
                
                [data-theme="dark"], .dark-mode, .dark {
                    --bg-color: #1a1a1a;
                    --text-color: #ffffff;
                    --link-color: #66ccff;
                    --border-color: #333333;
                }
                
                /* Fallback colors for elements that might be invisible */
                * {
                    color: inherit;
                }
                
                /* Ensure links are visible */
                a { color: var(--link-color, #0066cc); }
                a:visited { color: var(--link-color, #0066cc); }
                
                /* Ensure borders are visible */
                table, th, td, .border { border-color: var(--border-color, #cccccc); }
                """
            theme_fix_css.append(theme_css_content)
            head.append(theme_fix_css)
        
        # Create mapping of heading text to reference keys
        heading_map = {}
        for heading_data in headings:
            title = heading_data.get('title', '').strip()
            reference_key = heading_data.get('reference_key', '')
            if title and reference_key:
                heading_map[title] = reference_key
        
        # Add copy buttons to headings
        headings_enhanced = 0
        heading_tags = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        
        for heading_element in heading_tags:
            heading_text = clean_heading_text(heading_element.get_text())
            
            if heading_text in heading_map:
                reference_key = heading_map[heading_text]
                
                # Create copy button element
                copy_button = soup.new_tag('button')
                copy_button['class'] = 'copy-ref-btn'
                copy_button['onclick'] = f"copyToClipboard('{reference_key}')"
                copy_button['title'] = f"Copy reference: {reference_key}"
                copy_button['style'] = "margin-left: 8px; padding: 2px 6px; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 0.8em;"
                copy_button.string = '📋'
                
                # Insert button right after the heading
                heading_element.insert_after(copy_button)
                headings_enhanced += 1
        
        # Add JavaScript and CSS for copy functionality
        head = soup.find('head')
        if head:
            # Add CSS for copy buttons
            css_style = soup.new_tag('style')
            css_style['type'] = 'text/css'
            copy_btn_css = """
                .copy-ref-btn {
                    margin-left: 8px !important;
                    padding: 2px 6px !important;
                    background: #007bff !important;
                    color: white !important;
                    border: none !important;
                    border-radius: 3px !important;
                    cursor: pointer !important;
                    font-size: 0.8em !important;
                    opacity: 0.7;
                    transition: opacity 0.2s;
                    vertical-align: middle;
                }
                .copy-ref-btn:hover {
                    opacity: 1 !important;
                    background: #0056b3 !important;
                }
                .copy-ref-btn:active {
                    background: #004085 !important;
                }
                """
            css_style.append(copy_btn_css)
            head.append(css_style)
            
            # Add JavaScript for clipboard functionality
            js_script = soup.new_tag('script')
            js_script['type'] = 'text/javascript'
            js_content = """
                function copyToClipboard(text) {
                    if (navigator.clipboard && window.isSecureContext) {
                        navigator.clipboard.writeText(text).then(function() {
                            console.log('Copied to clipboard: ' + text);
                        }, function(err) {
                            console.error('Failed to copy: ', err);
                        });
                    } else {
                        // Fallback for older browsers
                        var textArea = document.createElement('textarea');
                        textArea.value = text;
                        textArea.style.position = 'fixed';
                        textArea.style.left = '-999999px';
                        textArea.style.top = '-999999px';
                        document.body.appendChild(textArea);
                        textArea.focus();
                        textArea.select();
                        try {
                            document.execCommand('copy');
                            console.log('Copied to clipboard: ' + text);
                        } catch (err) {
                            console.error('Failed to copy: ', err);
                        }
                        document.body.removeChild(textArea);
                    }
                }
                """
            js_script.append(js_content)
            head.append(js_script)
        
        # Save the complete enhanced HTML
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(str(soup))
        
        print(f"Complete enhanced webpage saved to {output_path}")
        print(f"Added copy buttons to {headings_enhanced} headings")
        print(f"Embedded CSS stylesheets and images for offline viewing")
        return True
            
    except Exception as e:
        print(f"Error creating enhanced webpage: {e}")
        return False


def url_to_filename(url: str) -> str:
    """
    Convert URL to a safe filename.
    
    Args:
        url (str): URL to convert
        
    Returns:
        str: Safe filename based on URL
    """
    parsed = urlparse(url)
    # Use domain and path, remove special characters
    filename = f"{parsed.netloc}{parsed.path}".replace('/', '_').replace('.', '_')
    # Remove multiple underscores and clean up
    filename = re.sub(r'_+', '_', filename).strip('_')
    return filename or "website"


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Extract headings from websites with multiple output formats',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python web_outline_extractor.py https://example.com
  python web_outline_extractor.py https://example.com -md
  python web_outline_extractor.py https://example.com -full

Output modes:
  Default: Creates outline HTML + JSON
  -md:     Creates Markdown outline + JSON  
  -full:   Creates enhanced full webpage + JSON
        """
    )
    parser.add_argument('url', nargs='?', default='https://callmepartario.github.io/og-csrd/',
                       help='URL of website to process (default: og-csrd)')
    parser.add_argument('-md', '--markdown', action='store_true',
                       help='Output Markdown outline instead of HTML outline')
    parser.add_argument('-full', '--full-webpage', action='store_true',
                       help='Create enhanced full webpage copy with reference buttons')
    
    args = parser.parse_args()
    target_url = args.url
    use_markdown = args.markdown
    use_full_webpage = args.full_webpage
    
    # Validate mutually exclusive options
    if use_markdown and use_full_webpage:
        print("Error: -md and -full options are mutually exclusive")
        parser.print_help()
        exit(1)
    
    try:
        print(f"Extracting headings from {target_url}...")
        
        # Fetch webpage content once (fetch-once-analyze-locally approach)
        raw_html, soup = fetch_webpage(target_url)
        
        # Extract headings from parsed content 
        headings = extract_headings_from_soup(soup)
        print_heading_outline(headings)
        
        # Always save JSON for AI consumption
        base_filename = url_to_filename(target_url)
        # Ensure files are created in current working directory (where script was called from)
        current_dir = os.getcwd()
        json_filename = os.path.join(current_dir, f"{base_filename}_headings.json")
        save_headings_json(headings, json_filename, target_url)
        
        # Choose output format based on flags
        if use_full_webpage:
            # Full webpage mode - enhanced webpage with copy buttons
            # Use cached raw HTML for efficiency
            full_filename = os.path.join(current_dir, f"{base_filename}_modified.html")
            save_headings_full_html(headings, full_filename, target_url, raw_html)
            print(f"\nOutput formats: Enhanced full webpage + JSON")
            print(f"Enhanced webpage: {full_filename}")
        elif use_markdown:
            # Markdown mode - outline in markdown format
            md_filename = os.path.join(current_dir, f"{base_filename}_headings.md")
            save_headings_markdown(headings, md_filename, target_url)
            print(f"\nOutput formats: Markdown outline + JSON")
        else:
            # Default mode - outline in HTML format
            html_filename = os.path.join(current_dir, f"{base_filename}_headings.html")
            save_headings_html(headings, html_filename, target_url)
            print(f"\nOutput formats: HTML outline + JSON (use -md for Markdown, -full for enhanced webpage)")
        
        print(f"JSON data: {json_filename}")
        print(f"\nProcessing complete!")
        
    except Exception as e:
        print(f"Error: {e}")