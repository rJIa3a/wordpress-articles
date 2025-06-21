<?php
use PHPUnit\Framework\TestCase;
require_once __DIR__ . '/../context-linker/includes/linker-utils.php';

class ContextLinkerTest extends TestCase {
    public function testInsertLink() {
        $content = 'Это тестовая статья о WordPress.';
        $anchor = 'тестовая статья';
        $url = 'https://example.com';
        $result = cl_insert_link( $content, $anchor, $url );
        $this->assertStringContainsString('<a href="https://example.com">тестовая статья</a>', $result);
    }

    public function testLoadData() {
        $data = cl_load_data( __DIR__ . '/../context_links.json' );
        $this->assertIsArray($data);
    }
}
